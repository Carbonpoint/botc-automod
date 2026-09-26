"""HTTP + WebSocket server (Starlette: pure Python, so it also runs on Android).

Each player's browser holds a token. The server sends every player a
personal view after each change, so no client ever receives another
player's secrets. Games are saved to disk after each change and reload
when the server restarts.
"""

from __future__ import annotations

import asyncio
import secrets
import io
import json
import logging
import os
import pickle
from contextlib import asynccontextmanager
from pathlib import Path

import segno
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from .editions import EDITIONS
from .game import SCHEMA, Game, GameError, NameTaken, new_code

log = logging.getLogger("botc")
STATIC = Path(__file__).parent / "static"
DATA = Path(os.environ.get("BOTC_DATA", Path.home() / ".local/share/botc-automod"))
DEBUG = os.environ.get("BOTC_DEBUG") == "1"

games: dict[str, Game] = {}
ARTIST = None                 # the Artist's question translator, set by main() (see artist/)
previews: dict[tuple[str, str], dict] = {}   # (game code, player id) -> the last translated question
karma: dict[str, int] = {}    # player name (lower case) -> karma, kept across games
sockets: dict[str, dict[str, set[WebSocket]]] = {}   # code -> player id -> sockets


def save(game: Game) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / f"{game.code}.pkl.tmp"
    tmp.write_bytes(pickle.dumps(game))
    tmp.replace(DATA / f"{game.code}.pkl")


def load_all() -> None:
    if not DATA.exists():
        return
    for f in DATA.glob("*.pkl"):
        try:
            g = pickle.loads(f.read_bytes())
        except Exception as e:  # a stale save from an old version
            log.warning("skipping %s: %s", f.name, e)
            continue
        if getattr(g, "schema", 1) != SCHEMA:
            log.warning("skipping %s: saved by an older version", f.name)
            continue
        for p in g.players.values():
            p.connected = False
        g.artist_ready = ARTIST is not None
        games[g.code] = g


def karma_file() -> Path:
    return DATA / "karma.json"


def load_karma() -> None:
    try:
        karma.update(json.loads(karma_file().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


def sync_karma(game: Game) -> None:
    changed = False
    for p in game.players.values():
        if karma.get(p.name.lower()) != p.karma:
            karma[p.name.lower()] = p.karma
            changed = True
    if changed:
        DATA.mkdir(parents=True, exist_ok=True)
        karma_file().write_text(json.dumps(karma, indent=1), encoding="utf-8")


async def broadcast(game: Game) -> None:
    game.version += 1
    save(game)
    sync_karma(game)
    for pid, conns in list(sockets.get(game.code, {}).items()):
        if pid not in game.players:
            for ws in list(conns):
                await ws.close(code=4001)
            continue
        msg = {"type": "state", "state": game.view_for(pid)}
        for ws in list(conns):
            try:
                await ws.send_json(msg)
            except Exception:
                conns.discard(ws)


async def ticker() -> None:
    while True:
        await asyncio.sleep(0.5)
        for g in list(games.values()):
            try:
                if g.tick():
                    await broadcast(g)
            except Exception:
                log.exception("tick failed for %s", g.code)


async def heartbeat() -> None:
    """Push the timer to everyone once a second."""
    while True:
        await asyncio.sleep(1)
        for g in list(games.values()):
            if g.phase in ("lobby", "ended") or not sockets.get(g.code):
                continue
            r = g.remaining()
            msg = {"type": "timer", "timer": None if r is None else round(r), "paused": g.paused_left is not None}
            for conns in sockets[g.code].values():
                for ws in list(conns):
                    try:
                        await ws.send_json(msg)
                    except Exception:
                        conns.discard(ws)


@asynccontextmanager
async def lifespan(app: Starlette):
    load_all()
    load_karma()
    tasks = [asyncio.create_task(ticker()), asyncio.create_task(heartbeat())]
    yield
    for t in tasks:
        t.cancel()


async def body_name(request: Request) -> tuple[str, str]:
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "Bad request.") from None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise HTTPException(400, "Please enter a name.")
    return data["name"], str(data.get("edition", "tb"))


def _game(code: str) -> Game:
    g = games.get(code.upper())
    if not g:
        raise HTTPException(404, "No game with that code.")
    return g


async def index(request: Request) -> FileResponse:
    return FileResponse(STATIC / "index.html")


async def info(request: Request) -> JSONResponse:
    """The address other devices should open (the host may be on localhost)."""
    from . import public_url
    from .artist.config import describe, load

    return JSONResponse({"join_url": public_url(request.url.port or 80),
                         "artist": describe(load()) if ARTIST is not None else "no model"})


async def list_games(request: Request) -> JSONResponse:
    return JSONResponse([{"code": g.code, "edition": g.edition.name, "players": len(g.players),
                          "host": g.host.name if g.host else "", "phase": g.phase}
                         for g in sorted(games.values(), key=lambda g: -g.created) if g.phase == "lobby"])


async def create_game(request: Request) -> JSONResponse:
    name, edition = await body_name(request)
    if edition not in EDITIONS:
        raise HTTPException(400, "Unknown edition.")
    g = Game(new_code(set(games)), edition)
    g.artist_ready = ARTIST is not None
    try:
        p = g.join(name, is_host=True)
    except GameError as e:
        raise HTTPException(400, str(e)) from None
    p.karma = karma.get(p.name.lower(), 0)
    games[g.code] = g
    save(g)
    return JSONResponse({"code": g.code, "token": p.token, "player": p.id})


async def join_game(request: Request) -> JSONResponse:
    g = _game(request.path_params["code"])
    name, _ = await body_name(request)
    try:
        p = g.join(name)
    except NameTaken:
        # The name is in the game already: this is someone coming back.
        try:
            kind, value = g.rejoin(name)
        except GameError as e:
            raise HTTPException(400, str(e)) from None
        await broadcast(g)
        if kind == "pending":
            return JSONResponse({"code": g.code, "pending": value})
        return JSONResponse({"code": g.code, "token": value, "rejoined": True})
    except GameError as e:
        raise HTTPException(400, str(e)) from None
    p.karma = karma.get(p.name.lower(), 0)
    await broadcast(g)
    return JSONResponse({"code": g.code, "token": p.token, "player": p.id})


async def rejoin_status(request: Request) -> JSONResponse:
    g = _game(request.path_params["code"])
    try:
        return JSONResponse(g.rejoin_status(request.path_params["rid"]))
    except GameError as e:
        raise HTTPException(404, str(e)) from None


async def editions(request: Request) -> JSONResponse:
    return JSONResponse([{"id": e.id, "name": e.name} for e in EDITIONS.values()])


async def almanac(request: Request) -> JSONResponse:
    eid = request.path_params["eid"]
    if eid not in EDITIONS:
        raise HTTPException(404, "Unknown edition.")
    return JSONResponse(EDITIONS[eid].almanac())


async def qr(request: Request) -> Response:
    buf = io.BytesIO()
    segno.make(request.query_params.get("url", ""), error="m").save(
        buf, kind="svg", scale=6, border=2, dark="#111", light="#fff")
    return Response(buf.getvalue(), media_type="image/svg+xml")


async def debug_role(request: Request) -> JSONResponse:
    """Test hook: give a player a character. Only with BOTC_DEBUG=1."""
    g = _game(request.path_params["code"])
    p = g.by_name(request.query_params["player"])
    role = request.query_params["role"]
    p.role = p.shown = role
    p.alignment = g.edition.roles[role].team
    await broadcast(g)
    return JSONResponse({"ok": True})


async def debug(request: Request) -> JSONResponse:
    g = _game(request.path_params["code"])
    return JSONResponse({"grimoire": [{"name": p.name, "role": p.role, "shown": p.shown, "alive": p.alive}
                                      for p in g.seated()],
                         "estate": {k: v for k, v in g.estate.items() if k != "reg"}})


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def _find(code: str, token: str):
    g = games.get(code.upper())
    if not g:
        return None, None
    p = next((p for p in g.players.values() if p.token == token), None)
    return g, p


HOST_ONLY = {"room", "start", "kick", "pause", "resume", "add_time", "advance", "setting", "end", "mode",
             "begin", "set_character", "st_set", "edit_pending", "add_pending", "send_pending",
             "st_kill", "st_revive", "st_message", "st_win", "edition", "st_answer", "st_execute"}


def handle(g: Game, pid: str, msg: dict) -> None:
    t = msg.get("type")
    me = g.p(pid)
    if t in HOST_ONLY and not me.is_host:
        raise GameError("Only the host can do that.")
    match t:
        case "seat":
            g.claim_seat(pid, msg.get("seat"))
        case "prefs":
            g.set_prefs(pid, msg.get("team", "any"), msg.get("style", "any"))
        case "task":
            g.submit_task(pid, msg["task"], msg.get("response"))
        case "nominate":
            g.nominate(pid, msg["target"])
        case "vote":
            g.vote(pid, bool(msg.get("yes")))
        case "slayer":
            g.slayer_claim(pid, msg["target"])
        case "leave":
            g.leave(pid)
        case "rejoin_answer":
            req = g.estate.get("rejoins", {}).get(msg["request"])
            if req is None:
                raise GameError("That request is already answered.")
            # The host answers for players; anyone else in the game answers for the host.
            if req["pid"] == pid or (not me.is_host and not g.p(req["pid"]).is_host):
                raise GameError("Only the host can answer that.")
            g.answer_rejoin(msg["request"], bool(msg.get("allow")))
        case "artist_confirm":
            prev = previews.pop((g.code, pid), None)
            if not prev or prev["id"] != msg.get("preview"):
                raise GameError("Check your question again first.")
            g.day_action(pid, "artist", {"text": prev["text"], "query": prev["query"]})
        case "day_action":
            g.day_action(pid, msg["key"], msg.get("payload") or {})
        case "edition":
            g.set_edition(msg["edition"])
        case "st_answer":
            g.st_answer(msg["request"], msg.get("text", ""))
        case "st_execute":
            g.st_execute(msg["player"])
        case "room":
            g.set_room(msg["shape"], msg.get("seats", 0), msg.get("rows", 0),
                       msg.get("cols", 0), msg.get("cells"))
        case "start":
            g.start()
        case "kick":
            g.kick(msg["player"])
        case "pause":
            g.pause()
        case "resume":
            g.resume()
        case "add_time":
            g.add_time(float(msg.get("seconds", 30)))
        case "advance":
            g.advance()
        case "setting":
            g.set_setting(msg["key"], msg["value"])
        case "end":
            g.force_end()
        case "mode":
            g.set_mode(msg["mode"])
        case "begin":
            g.begin_game()
        case "set_character":
            g.set_character(msg["player"], msg["role"], msg.get("shown"))
        case "st_set":
            g.st_set(msg["key"], msg["value"])
        case "edit_pending":
            g.edit_pending(msg["player"], int(msg.get("index", 0)), list(msg["lines"]))
        case "add_pending":
            g.add_pending(msg["player"], msg["text"])
        case "send_pending":
            g.send_pending()
        case "st_kill":
            g.st_kill(msg["player"])
        case "st_revive":
            g.st_revive(msg["player"])
        case "st_message":
            g.st_message(msg["player"], msg["text"])
        case "st_win":
            g.st_win(msg["team"], msg.get("reason", ""))
        case _:
            raise GameError("Unknown action.")


async def artist_preview(ws: WebSocket, g: Game, p, text: str) -> None:
    """Translate an Artist's question and show them the reading. Nothing is spent yet."""
    from .artist.query import World, render

    if ARTIST is None or g.mode != "auto":
        await ws.send_json({"type": "error", "message": "No question model is set up."})
        return
    if not any(a["key"] == "artist" for a in g.edition.day_actions(g, p)):
        await ws.send_json({"type": "error", "message": "You cannot ask the Artist question now."})
        return
    if not text.strip():
        await ws.send_json({"type": "error", "message": "Type your question first."})
        return
    world = World.from_game(g)
    try:
        query, _ = await asyncio.to_thread(ARTIST.translate, world, p.name, text)
    except Exception:
        log.exception("artist translation failed")
        query = None
    ok = bool(query) and query["op"] != "unanswerable"
    pid = secrets.token_hex(3)
    if ok:
        previews[(g.code, p.id)] = {"id": pid, "text": text, "query": query}
    await ws.send_json({"type": "artist_preview", "id": pid, "text": text, "ok": ok,
                        "reading": render(query, world, p.name) if ok else ""})


async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    g, p = _find(ws.path_params["code"], ws.query_params.get("token", ""))
    if not p:
        await ws.send_json({"type": "gone"})
        await ws.close(code=4004)
        return
    conns = sockets.setdefault(g.code, {}).setdefault(p.id, set())
    conns.add(ws)
    p.connected = True
    await broadcast(g)
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                continue
            if p.id not in g.players:
                break
            if msg.get("type") == "artist_preview":
                await artist_preview(ws, g, p, str(msg.get("text", ""))[:300])
                continue
            try:
                handle(g, p.id, msg)
            except GameError as e:
                await ws.send_json({"type": "error", "message": str(e)})
                continue
            except (KeyError, TypeError, ValueError):
                await ws.send_json({"type": "error", "message": "Bad request."})
                continue
            await broadcast(g)
    except WebSocketDisconnect:
        pass
    finally:
        conns.discard(ws)
        if p.id in g.players:
            p.connected = bool(conns)
            await broadcast(g)


routes = [
    Route("/", index),
    Route("/api/info", info),
    Route("/api/games", list_games, methods=["GET"]),
    Route("/api/games", create_game, methods=["POST"]),
    Route("/api/games/{code}/join", join_game, methods=["POST"]),
    Route("/api/games/{code}/rejoin/{rid}", rejoin_status),
    Route("/api/editions", editions),
    Route("/api/editions/{eid}", almanac),
    Route("/api/qr", qr),
    WebSocketRoute("/ws/{code}", ws_endpoint),
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]
if DEBUG:
    routes[:0] = [Route("/api/debug/{code}/role", debug_role, methods=["POST"]), Route("/api/debug/{code}", debug)]

app = Starlette(routes=routes, lifespan=lifespan, exception_handlers={HTTPException: http_error})
