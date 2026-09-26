"""botc-automod: a self-hosted, automated storyteller for Blood on the Clocktower."""

import argparse
import socket


def lan_address() -> str:
    """Best guess at this machine's LAN address (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def setup_artist(force: bool, data_dir):
    """Settle the Artist's language model: ask on first run (or --setup), then build and test it."""
    import sys
    import time

    from .artist import config
    from .artist.query import Seat, World
    from .artist.translate import OpenAITranslator, make_translator

    cfg = config.load()
    interactive = sys.stdin.isatty() and not __import__("os").environ.get("BOTC_ARTIST")
    if (force or not cfg) and interactive:
        cfg = config.wizard()
        config.save(cfg)
    cfg = cfg or {"kind": "none"}
    print(f"  Artist questions: {config.describe(cfg)}   (change with --setup)")
    if cfg.get("kind", "none") == "none":
        return None
    try:
        if cfg["kind"] == "packaged":
            from .artist.runtime import LocalServer

            server = LocalServer(data_dir / "llm", cfg.get("model", ""))
            server.start()
            translator = OpenAITranslator(server.url, "packaged", compact=True)
        else:
            translator = make_translator(cfg)
        world = World([Seat(n, "chef", "townsfolk", "good", True, False) for n in ("Ann", "Ben", "Cat", "Dan", "Eve")],
                      {"chef": ("Chef", "townsfolk"), "imp": ("Imp", "demon")})
        start = time.time()
        q, raw = translator.translate(world, "Ann", "Is Ben evil?")
        if not q or q.get("op") != "is_team":
            raise RuntimeError(f"the test question came back wrong: {raw[:120]!r}")
        print(f"  Artist model test passed in {time.time() - start:.1f}s.")
        return translator
    except Exception as e:  # never block the game on the Artist
        print(f"  Artist model unavailable ({e}). The Artist is left out of automated games.")
        return None


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="Run the Blood on the Clocktower automod server.")
    ap.add_argument("--host", default="0.0.0.0", help="address to listen on (default: all)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-qr", action="store_true", help="do not print the join QR code")
    ap.add_argument("--setup", action="store_true", help="ask again how the Artist's questions are answered")
    args = ap.parse_args()

    from . import server

    server.ARTIST = setup_artist(args.setup, server.DATA)
    url = public_url(args.port)
    print(f"\n  botc-automod is running. Players scan this code, or open {url}\n  (phones must be on the same network)\n")
    if not args.no_qr:
        import segno
        segno.make(url, error="l").terminal(compact=True)
        print()
    uvicorn.run(server.app, host=args.host, port=args.port, log_level="warning")


def public_url(port: int) -> str:
    """The address players open. BOTC_PUBLIC_URL overrides it (Docker, reverse proxies)."""
    import os

    return os.environ.get("BOTC_PUBLIC_URL") or f"http://{lan_address()}:{port}/"
