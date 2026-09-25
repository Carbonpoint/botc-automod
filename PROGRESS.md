# PROGRESS

Read README.md first.

## 2026-09-25: first working version

- The first attempt (a free-model session, same day) built nothing: its
  research agents hit a daily rate limit. This version started fresh.
- Built: engine, Trouble Brewing (all 22 characters), preference deal,
  4 room shapes, decoy tasks, two-stage nights, nominations and voting,
  Slayer claims, host script and controls, save and reload, phone web app.
- Verified: 71 pytest tests pass (rules plus 40 random full games).
  `scripts/smoke.py` (7 WebSocket bots) reached day 1. `scripts/ui_check.py`
  (5 headless browsers) reached a vote with no page errors.
- Not verified yet: a real game on real phones; reload after a server
  restart mid-game; the grid room shape in a browser.
- Port 8765 on this machine is taken by another service on the Tailscale
  address. The default port is 8000. Tests used 8777.

## Open ideas

- Travellers and Fabled; more editions (Bad Moon Rising, Sects & Violets).
- Clockwise sequential voting (a hand that moves around the circle).
- Sound cues for dawn and dusk on the host phone.
- A host option to swap two seats after the game starts.
- Rejoin on a new device (today a player is tied to their browser storage).
