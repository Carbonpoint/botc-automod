"""Drive a real server with 7 bots through setup, night 1 and into day 1."""
import asyncio, json, sys, urllib.request
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"

def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

async def bot(name, code, token, idx, states, host=False):
    uri = BASE.replace("http", "ws") + f"/ws/{code}?token={token}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "seat", "seat": idx}))
        await ws.send(json.dumps({"type": "prefs", "team": "evil" if idx == 2 else "any", "style": "any"}))
        started = False
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 60))
            if m["type"] == "error":
                print(name, "ERROR", m["message"])
            if m["type"] != "state":
                continue
            s = m["state"]; states[name] = s
            g = s["game"]
            if host and g["phase"] == "lobby" and not started and sum(p["seat"] is not None for p in s["players"]) == 7 \
                    and all(p["ready"] for p in s["players"]):
                started = True
                await ws.send(json.dumps({"type": "start"}))
            t = s["task"]
            if g["phase"] == "night" and t:
                if t["kind"] == "choose": resp = t["candidates"][:t["pick"]]
                elif t["kind"] == "decoy": resp = t["options"][0]
                else: resp = True
                await ws.send(json.dumps({"type": "task", "task": t["id"], "response": resp}))
            if g["phase"] == "day":
                return

async def main():
    host = post("/api/games", {"name": "Host"})
    code = host["code"]
    creds = [("Host", host["token"])] + [(n, post(f"/api/games/{code}/join", {"name": n})["token"]) for n in "Ann Ben Cat Dan Eve Fay".split()]
    states = {}
    await asyncio.gather(*(bot(n, code, t, i, states, host=(i == 0)) for i, (n, t) in enumerate(creds)))
    for n, s in states.items():
        print(f"{n:5} {s['me']['role']['name']:15} notebook: {[e['text'][:70] for e in s['me']['log'][1:]]}")
    print("HOST SCRIPT:"); [print("  ", e["text"]) for e in states["Host"]["host"]["script"]]
    assert all("grimoire" not in s for s in states.values())
    print("OK", code, states["Host"]["game"]["label"])

asyncio.run(main())
