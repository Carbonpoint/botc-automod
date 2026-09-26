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

## 2026-09-26 (evening): landing page, archive, pause, game files

- Landing page from the user's sketch: name card, join card, Join,
  Host a new game, Archive.
- Games are Markdown files (`src/botc_automod/archive.py`) in
  `DATA/games/{running,paused,completed}/`; old `*.pkl` saves move into
  `running/` at start. The save block is a zlib + base64 pickle, loaded by
  an unpickler that allows only `Game`, `Player` and `random.Random`.
- Join list: a trash button deletes a lobby (yes/no pop-up). Games in play
  are listed too, to rejoin. A browser keeps every token it held
  (`botc-tokens`), so after a pause or resume players go straight back.
- Host tab: Export as Markdown, Pause the game. The timer buttons are now
  "Pause timer" / "Resume timer". After a resume or a restart the timer
  waits for the host.
- Resume needs a token of a player in that game, or the host's name.
  Deleting a lobby and exporting archive files need no login (home LAN).
- Verified: 295 tests; `scripts/archive_check.py` (16 browser checks:
  delete, pause, resume, rejoin, crash restart, end, export, import);
  ui_check (auto and human) and rejoin_check with no page errors.
- The host tab is under the night screen, so the host pauses in the day.
- Morning narrator (setting `narrator`, on by default): at dawn the game
  stays in phase "day" with stage "narration" and no timer. A random seated
  player (`secrets`, not the game rng) gets a story from `narrator.py`;
  others see "listen". The narrator taps done (or the host skips, or the
  host's advance) and the day timer starts. Public day actions wait.
  Stories use only the victims' names; other names are random living players.
  Test builders set `narrator` to 0; half the random games turn it on.
- Sounds and vibration (`cue()` in app.js): Web Audio tones, no files.
  Night falls, dawn, narrator chosen, day, nominations, nominated, vote,
  end; day-timer warnings at 30 s and 10 s, ticks in a vote's last 5 s.
  No sound for night tasks (they only vibrate, as before). Per-phone
  on/off in the lobby and the Me tab (`botc-feel`).
- Verified: 300 tests; audit of 100 games per edition, 0 problems;
  ui_check (auto, human snv), rejoin_check, archive_check with no page
  errors. Sounds not heard by a person yet; vibration not felt on a phone.
- Themes (`narrator.THEMES`, `Game.theme`, lobby "Theme" card): "default"
  (Ravenswood Bluff) and "jojo" (Jo Jo's Mid-Autumn Festival: his rainy
  apartment in Ames, Iowa). The theme picks the narrator's story lines.

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
