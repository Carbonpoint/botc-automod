"""HTTP + WebSocket server.

Each player's browser holds a token. The server sends every player a
personal view after each change, so no client ever receives another
player's secrets. Games are saved to disk after each change and reload
when the server restarts.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import pickle
from contextlib import asynccontextmanager
from pathlib import Path

import segno
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .editions import EDITIONS
from .game import SCHEMA, Game, GameError, NameTaken, new_code

log = logging.getLogger("botc")
STATIC = Path(__file__).parent / "static"
DATA = Path(os.environ.get("BOTC_DATA", Path.home() / ".local/share/botc-automod"))
DEBUG = os.environ.get("BOTC_DEBUG") == "1"

games: dict[str, Game] = {}
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
async def lifespan(app: FastAPI):
    load_all()
    load_karma()
    tasks = [asyncio.create_task(ticker()), asyncio.create_task(heartbeat())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="botc-automod", lifespan=lifespan)


class NameIn(BaseModel):
    name: str
    edition: str = "tb"


def _game(code: str) -> Game:
    g = games.get(code.upper())
    if not g:
        raise HTTPException(404, "No game with that code.")
    return g


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info(request: Request) -> dict:
    """The address other devices should open (the host may be on localhost)."""
    from . import lan_address
    port = request.url.port or 80
    return {"join_url": f"http://{lan_address()}:{port}/"}


@app.get("/api/games")
def list_games() -> list[dict]:
    return [{"code": g.code, "edition": g.edition.name, "players": len(g.players),
             "host": g.host.name if g.host else "", "phase": g.phase}
            for g in sorted(games.values(), key=lambda g: -g.created) if g.phase == "lobby"]


@app.post("/api/games")
async def create_game(body: NameIn) -> dict:
    if body.edition not in EDITIONS:
        raise HTTPException(400, "Unknown edition.")
    g = Game(new_code(set(games)), body.edition)
    try:
        p = g.join(body.name, is_host=True)
    except GameError as e:
        raise HTTPException(400, str(e)) from None
    p.karma = karma.get(p.name.lower(), 0)
    games[g.code] = g
    save(g)
    return {"code": g.code, "token": p.token, "player": p.id}


@app.post("/api/games/{code}/join")
async def join_game(code: str, body: NameIn) -> dict:
    g = _game(code)
    try:
        p = g.join(body.name)
    except NameTaken:
        # The name is in the game already: this is someone coming back.
        try:
            kind, value = g.rejoin(body.name)
        except GameError as e:
            raise HTTPException(400, str(e)) from None
        await broadcast(g)
        if kind == "pending":
            return {"code": g.code, "pending": value}
        return {"code": g.code, "token": value, "rejoined": True}
    except GameError as e:
        raise HTTPException(400, str(e)) from None
    p.karma = karma.get(p.name.lower(), 0)
    await broadcast(g)
    return {"code": g.code, "token": p.token, "player": p.id}


@app.get("/api/games/{code}/rejoin/{rid}")
async def rejoin_status(code: str, rid: str) -> dict:
    g = _game(code)
    try:
        return g.rejoin_status(rid)
    except GameError as e:
        raise HTTPException(404, str(e)) from None


@app.get("/api/editions")
def editions() -> list[dict]:
    return [{"id": e.id, "name": e.name} for e in EDITIONS.values()]


@app.get("/api/editions/{eid}")
def almanac(eid: str) -> dict:
    if eid not in EDITIONS:
        raise HTTPException(404, "Unknown edition.")
    return EDITIONS[eid].almanac()


@app.get("/api/qr")
def qr(url: str) -> Response:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, dark="#111", light="#fff")
    return Response(buf.getvalue(), media_type="image/svg+xml")


if DEBUG:
    @app.get("/api/debug/{code}")
    def debug(code: str) -> dict:
        g = _game(code)
        return {"grimoire": [{"name": p.name, "role": p.role, "shown": p.shown, "alive": p.alive}
                             for p in g.seated()], "estate": {k: v for k, v in g.estate.items() if k != "reg"}}


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


@app.websocket("/ws/{code}")
async def ws_endpoint(ws: WebSocket, code: str, token: str) -> None:
    await ws.accept()
    g, p = _find(code, token)
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


app.mount("/static", StaticFiles(directory=STATIC), name="static")
