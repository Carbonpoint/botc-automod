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


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="Run the Blood on the Clocktower automod server.")
    ap.add_argument("--host", default="0.0.0.0", help="address to listen on (default: all)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-qr", action="store_true", help="do not print the join QR code")
    args = ap.parse_args()
    url = f"http://{lan_address()}:{args.port}/"
    print(f"\n  botc-automod is running. Players scan this code, or open {url}\n  (phones must be on the same network)\n")
    if not args.no_qr:
        import segno
        segno.make(url, error="l").terminal(compact=True)
        print()
    uvicorn.run("botc_automod.server:app", host=args.host, port=args.port, log_level="warning")
