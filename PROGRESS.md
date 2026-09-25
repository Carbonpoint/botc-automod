# PROGRESS

Read README.md first.

## 2026-09-25: three editions, two storyteller modes

- First attempt (a free-model session, same day) built nothing: its
  research agents hit a daily rate limit. This version started fresh.
- v1: engine, Trouble Brewing, preference deal, 4 room shapes, decoy
  tasks, two-stage nights, nominations and votes, phone web app.
- v2: human storyteller mode; wiki character data; terminal QR code.
- v3: a shared rules engine (`editions/rules.py`) with one class per
  character. Trouble Brewing was ported to it. Bad Moon Rising and
  Sects & Violets were added. Also: edition picker, new night task types
  (character, player + character, choose no one), day actions, storyteller
  requests and "execute now", a save-format version.
- Verified: 228 pytest tests pass. They include 120 random full games
  (3 editions, both modes) and a test per tricky rule. Headless browser
  runs of all three editions, and of Sects & Violets with a human
  storyteller, gave no page errors. A Gossip statement sent from the
  page reached the town log.
- Not verified yet: a real game on real phones; a server restart in the
  middle of a game; the grid room shape in a browser.
- Port 8765 on this machine is taken by another service on the Tailscale
  address. The default port is 8000. Tests used 8777.

## Known simplifications

- A Philosopher's gained choice ability acts in stage B of the night it
  is gained; its info arrives in the notebook at dawn.
- An exorcised Demon still sees its kill prompt (choices are
  simultaneous); it is told the Exorcist stopped it.
- A Moonchild or Klutz executed at the end of a day chooses during the
  night. A Moonchild choice counts that night only if made before stage A
  ends.
- Gossip and Artist statements from free text cannot be judged by the
  automod. A human storyteller judges them.

## Open ideas

- Travellers and Fabled; custom scripts mixing characters.
- Clockwise sequential voting (a hand that moves around the circle).
- Sound cues for dawn and dusk on the host phone.
- A host option to swap two seats after the game starts.
- Rejoin on a new device (today a player is tied to their browser storage).
