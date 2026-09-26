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

## 2026-09-26: fixes from the first real games

- Librarian told "no Outsiders" with a Recluse in play: a false
  registration could hide the only true match. Now it can only add a false
  one. The same flaw could tell an Investigator "no Minions" (a lone Spy).
- Demon bluffs option (on by default), bluffs on the Demon's Me tab.
- Artist dealt only with a human storyteller. LLM plan: docs/artist-llm.md.
- Karma from one scored night question per player per night; it tilts
  chance decisions and the deal. Kept per name across games.
- Rejoin by name (lobby: at once; in game: host approval); lobby Leave
  frees the name.
- Info audit (`src/botc_automod/audit.py`): a checker, separate from the
  engine's info code, re-derives every message from a snapshot. It caught
  the Librarian/Investigator flaw when the old code was put back. It also
  found a real bug: a Philosopher's gained death-trigger ability (Sage,
  Ravenkeeper, Klutz, Moonchild, Barber, Sweetheart, Saint) never fired.
  Fixed. The Undertaker now learns only about an executed player who died.
- Verified: 242 tests pass; the audit of 2,000 games per edition (see the
  commit message for counts); browser checks of all editions, the human
  storyteller, and rejoin, with no page errors.

## 2026-09-26 (later): Artist model, Docker, Android

- Artist: query language evaluated by the engine; translator backends
  (Ollama, OpenAI-compatible, Anthropic); first-run questions; confirm
  step in the page. Benchmarks of 14 off-the-shelf models and fine-tuned
  runs: see docs/artist-llm.md. Chosen: SmolLM2 135M run 3, 8-bit (90% / 94%
  right, 0.3 to 0.8 s on a 4-core CPU, 145 MB).
- Model file on stalker: `~/botc-train/runs/smol-135m-v3/model-Q8_0.gguf`.
  Published 2026-09-26 at https://huggingface.co/carbonpoint/botc-artist
  (public, the user approved); PACKAGED_REPO in artist/runtime.py points there.
- Server moved from FastAPI to Starlette (pure Python, runs on Android).
- Docker: Dockerfile + compose.yaml, tested with Podman.
- Android: android/ Java + Chaquopy app (foreground service, QR, browser
  link, Artist settings, bundled llama.cpp). Tested in an Android 11
  emulator on stalker (no KVM there, very slow): the server ran in the
  foreground service and 7 bots played night 1 through it. The emulator
  crashes on this Fedora host. Not yet run on a real phone.
- Seat maps draw one path with arrows through the seats in order.

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
