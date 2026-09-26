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
- Savant: `savant_facts` has many more kinds (exactly one evil of two,
  same team as you, neighbours, Minion/Demon in your clockwise half,
  Outsider count, the dead, today's nominators). Truth is always from the
  true state. With a human storyteller the request carries a suggested pair.
- Helpful narrator (`helper.py`, setting `helper`: 0 off, 1 learners the
  host marks, 2 everyone). One tip per player per day, by day only: a wiki
  tip for the believed character, a public-facts tip, and "speak with X"
  (good team: a sober good Townsfolk with chance 10% + 5% per karma,
  clamped 5-30%; evil: always random). With a chat-capable model
  (`Translator.chat`, not the packaged one) the player may add a question;
  the model sees only the player's own knowledge with other names hidden,
  and an answer that names a player is dropped. Tips go into the notebook.
- Tip models (`scripts/helper_bench.py` on stalker, 6 questions incl. 4
  prying ones): with no checks, gemma3:1b and llama3.2:3b answered "Is Eve
  evil?" with "Definitely"/"Yes." (made up, but a learner would trust it),
  and qwen3:4b returned its reasoning as text. `safe_answer` now also drops
  answers that start with yes/no, state a verdict about a player, or talk
  about "the user". After that no answer was unsafe. Best: qwen3:1.7b
  (0.7-0.9 s, refuses politely). The packaged model cannot chat: offline
  tips only. No tip model was trained.

- Chat tab (`Game.send_chat`): group and private messages, 300 chars, one
  a second, none at night. Group: pop-up with text + sound + buzz. Private:
  quiet "New private message" pop-up (buzz only if the phone opts in).
  Host option `anon_chat`: messages without a name; the server strips the
  sender from every other view. Keywords are hidden in chat.
- Keyword tasks (`keywords.py`, option `irl_tasks`): a daily loop of
  in-person keyword swaps between humans; +2 / -1 / snoop +1, owner and
  receiver -1; 3 wrong tries a day.
- Agents (`agents.py`): the host adds agents to empty seats in the lobby.
  They answer night tasks (evil never targets its team), claim characters
  (evil: Demon bluffs), share info, nominate, defend, vote, narrate, and
  use forced/Savant/Juggler/Slayer abilities. Good agents get a HUNCH of
  0.25 (lean toward the truth when nominating and voting): 240 agent games
  gave good 49%. With a chat model agents talk in their own words
  (`llm_prompt`/`llm_check`; an evil agent naming its true character is
  dropped). Tested with qwen3:1.7b on stalker: no secrets given away.
  Agents take no part in keyword tasks or tips, and no human can rejoin as one.

## 2026-09-26 (night): karma arcade

- Start page link "Karma arcade" (`static/arcade.js`, `arcade.py`, data in
  `DATA/arcade.json`). Games: Flappy Bat, Night Runner (the dinosaur game),
  2047 (2048 with odd tiles 2^n-1; a+a -> 2a+1), Blocks (small Tetris with
  a button pad), Snake, Town Pool.
- Karma per name per day: +1 first real game (a minimum score per game),
  +1 a new record on a game's board, +1 per 3 pool balls; cap 3 a day.
  `server.add_karma` also updates a seat in a live game, so `sync_karma`
  does not write the old value back.
- Scores come from the browser. The server refuses a score too high for
  the round's time (rate + slack per game). No other anti-cheat (home LAN).
- Town Pool: one shared table. Server physics (`arcade.simulate`, 0.03 s a
  shot); the frames of the last shot go to every phone for playback. A
  shot names the table version; the last shooter waits 20 s unless someone
  else shoots. Pocketed ball +1 point, cue ball -1 and back on the spot,
  empty table -> new rack. Stroke: thumb down, pull back (power), slide
  forward past the start; drift off the line bends the angle. Portrait
  phones see the table turned on its side.
- Verified: 13 new tests (394 in all pass, 1 skipped); `scripts/arcade_check.py`
  (every game ends, a pool shot, karma, no page errors) at 390x844.
  Not played by a person on a real phone yet: the feel of the pool stroke
  and game speeds are untuned.
- Host option `show_votes` (on by default): during a vote each seat on the
  Town map, and each Grimoire row, shows 💀 (execute) or 😇 (no) as votes
  come in. Off: votes stay hidden until the vote closes. Checked in ui_check.
- Emma's "Annoy Tommy?" button moved from the Characters tab to the bottom
  of the Me tab: full width, dark grey on dark, so it is easy to miss.
- The "On this phone" card is only on the Me tab and in the lobby (not Chat).
- The arcade opens inside a game too (Me tab and lobby link; the player's
  game name is used). It closes by itself at night, at a vote, during the
  dawn story and in setup. Arcade karma broadcasts to that player's games.
- ui_check now seats Emma and Tommy and checks the button, the Chat tab
  and the in-game arcade (it closes when the vote opens).

## 2026-09-26 (late): arcade during the game

- The user played real games: sounds work, vibration works on Android,
  and the arcade runs nicely.
- The arcade no longer closes by itself in a game. It stays open at
  night, in votes and during the dawn story (not for a storyteller).
- When the game needs the player, a gold bar at the top says why and has
  "Go to game" (`gameCall`/`callBar` in app.js). Reasons: a night task,
  the narrator's story, your own defense, a vote you have not cast. The
  phone buzzes when the reason changes. "Go to game" ends the round.
- Verified: 396 tests pass, 1 skipped; ui_check (Lena sees "Vote on Kofi."
  over the arcade, taps the bar, votes) and arcade_check, no page errors.
  Not checked in a browser: the bar at night.

## 2026-09-26 (late): jump scares and the falling pipe

- Host options (lobby card "Jump scares", `scares.py`): `scares` 0 off,
  1 low, 2 medium, 3 high = chance 0.25 / 0.5 / 1.0 per human player per
  day. `pipe` (on by default): one player hears a falling metal pipe once
  a game (chance 0.3 on day 1, 0.5 on day 2, 1.0 from day 3). Target:
  `estate["pipe_target"]` (host picks), else a seated Tommy (`is_tommy`).
- Planned at the start of each day (after the story), each in its own
  5 s slot 20-240 s in, so no two phones go off together. Dropped at night.
  The phone waits while it has a night task, a vote, or the dawn story.
  It shows each scare once (`botc-scared` in localStorage). Agents: none.
- Screen: random scary emoji, often with a creepy line, red flashes and
  shake, 1.8 s (a tap ends it); a falling scream. Pipe: a synthesized
  metal bar (free-bar modes 1, 2.756, 5.404, 8.933) bouncing 6 times.
  Both are Web Audio, no files, and follow the phone's sound/buzz settings.
- Verified: 405 tests pass, 1 skipped; ui_check shows the options card,
  Tommy as the default pipe target, a scare on Jess, no page errors.
  Not heard by a person yet: the scream and the pipe.

## 2026-09-26 (late): agents answer the chat

- The user asked why agents seemed unresponsive in the chat. Two reasons:
  agents never read the chat, and the packaged Artist model cannot chat,
  so all agent talk was fixed lines.
- Now (`agents._heard` / `_replies`): an agent answers a private message
  (privately), a group message with its name, or a question to everyone
  (one or two agents; a plain message: 15% that one agent comments).
  2-6 s later, at most one answer per agent per 4 s. Nothing at night.
- Without a chat model: `_reply_text` picks lines by keywords (claim,
  info, a suspect, a defense, a greeting). Evil agents never suspect
  their team; good agents use the same HUNCH as for votes.
- With a chat model: the same prompt as other agent talk, with the
  message in it. qwen3:1.7b on stalker: 0.7-0.8 s per reply. It leaked
  evil secrets ("Clover is an Imp", "the evil ones are Clover and me").
  `llm_check` now drops, for evil agents, any evil character name
  (also plural), any teammate's name, tells like "real identity", and a
  sentence with "evil" and a first-person word. After that, no leak got
  through in the bench (`scripts/agent_talk_bench.py`, replies part).
- The user usually plays with the packaged model on a laptop CPU, so
  they got the fixed lines. Fixed below with the local chat model.
- Verified: 412 tests pass, 1 skipped; `scripts/agent_chat_check.py`
  (browser, human storyteller + agents): a town question, a named agent
  and a private message all got answers; no page errors.

## 2026-09-26 (late): local chat model next to the Artist model

- Option at server start (first run or `--setup`, `config.wizard_chat`;
  saved as "chat" in config.json; env `BOTC_CHAT`): Qwen3 1.7B Q4_K_M
  from unsloth/Qwen3-1.7B-GGUF, pinned commit d7f544e (1.11 GB, Apache-2.0).
  Asked only when the Artist model cannot chat (none or packaged).
- A second llama-server (`LocalServer.chat`, port 8780, ctx 4096, --jinja;
  thinking off per request with chat_template_kwargs). `server.CHAT` now
  writes all agent talk and tips; `ARTIST` only translates questions.
  Android: CHAT is the Artist model if it can chat; the app has no
  chat model option yet.
- Measured on this 4-core, 15 GB machine: downloads + start 19 s, test
  message 1.4-1.6 s; 28 agent replies: median 2.8 s, max 7.6 s (the first
  reply of each agent is slowest). The chat llama-server used 2.3 GB RSS,
  the Artist one 0.2 GB. llm_check dropped 7 of 28 (all evil leaks).
- One model slot: at dawn all agents claim at once and answers to people
  waited ~40 s. Now a priority queue (`server._talk_worker`): replies and
  defenses first; other talk older than 25 s uses its fixed line.
- Verified: 414 tests pass, 1 skipped; agent_chat_check with both models
  live: model-written answers to a named question and a private message
  (private), no page errors. Not run on the user's laptop yet.

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
