# botc-automod

A self-hosted server for playing Blood on the Clocktower at home. Everyone
sits in the same room and plays on their phone's web browser.

- **Editions:** Trouble Brewing, Bad Moon Rising, Sects & Violets (5 to 15
  players). The host picks one in the lobby.
- **Storyteller:** the host picks one of two modes in the lobby:
  - *Automated.* The server is the storyteller. The host also plays and
    learns nothing secret. The host only reads public lines aloud and
    controls the timer.
  - *Human.* The host is the storyteller and does not play. The server
    still does the work. The storyteller checks the deal, sees every
    night choice, and edits the night results before players get them.

**Install:** [on a fresh computer](#install-on-a-fresh-computer) (Windows, macOS, Linux) ·
[with Docker](#docker) · [Android phone as the server](#android-host-app) ·
[Artist question model](#artist-question-model)

## Run it

```sh
cd botc-automod
uv run botc-automod              # listens on all addresses, port 8000
uv run botc-automod --port 8080  # another port
uv run botc-automod --no-qr      # skip the terminal QR code
uv run botc-automod --setup      # ask again which model answers the Artist
```

The server prints the join address and a QR code in the terminal.
Players scan it or type the address. The host's lobby screen shows the
same QR code. Phones must be on the same network as the server. If
phones cannot connect, a firewall is blocking the port (see the install
steps for your system).

Games are saved in the data folder (`~/.local/share/botc-automod/` on
Linux and macOS, `%USERPROFILE%\.local\share\botc-automod` on Windows)
after every change, and reload when the server restarts. Set `BOTC_DATA`
to save elsewhere. Saves from an older format are skipped. Set
`BOTC_DEBUG=1` to enable debug endpoints that show the full Grimoire.
Never enable it during a real game.

## How a game goes

1. **Lobby.** One player taps *Host a new game*. The host picks the
   edition, the options (below) and the storyteller mode. Others scan the
   QR code or join with the 4-letter code.

   Coming back: in the lobby, a player who lost the page joins again with
   the same name and gets their seat back. After the start, the host must
   approve it (the host's own return is approved by any other player).
   *Leave this game* in the lobby frees the name and the seat.
2. **Room.** The host picks the room shape: circle, horseshoe, square, or
   grid. For a grid, the host sets rows and columns and taps the seat
   squares in clockwise order. Each player taps their own seat. Seat order
   matters: many characters use neighbours.
3. **Preferences.** Each player picks a team (good, evil, no preference)
   and a style (chill, thinking, no preference). The deal is random but
   honours these where it can: team first, then style.
4. **Setup (human storyteller only).** The storyteller sees the deal. They
   can change any character, the Fortune Teller's red herring and the
   Demon bluffs. Then they begin the first night.
5. **Nights.** Every phone gets a task, so nobody can tell who acts.
   Characters with a night action choose players or characters. Everyone
   else gets a quick maths or trivia question. At the end of each night,
   everyone gets one scored "night question" for karma. Each night has
   two stages:
   - Stage A: all choices, and on the first night with 7+ players, the
     evil team's info and the Demon's bluffs.
   - Stage B: information, and second choices that depend on stage A (a
     dead Ravenkeeper, a Barber swap, a Philosopher's new ability).

   A stage ends when everyone is done (after at least `night_min` seconds)
   or at `night_max`. At that time, optional abilities pass and required
   choices are made at random. With a human storyteller, the night pauses
   after each stage until the storyteller sends the results.
6. **Days.** Discussion, then nominations. A nominator taps a player; the
   town hears the accusation and defence; everyone votes on their phone.
   Dead players have one ghost vote. The player with the most votes (at
   least half the living, and no tie) is executed at the end of the day.
7. **Day abilities** appear on the Town screen:
   - Public claims anyone may make as a bluff: Slayer shot, Gossip
     statement, Juggler guesses (day 1).
   - Private abilities for the real character only: Artist question,
     Savant visit.
   - Forced choices when a Klutz or Moonchild learns they died.
8. **End.** When a team wins, every phone shows the full Grimoire.

## Install on a fresh computer

You need two tools. **uv** runs the project and installs the right Python
by itself, so you do not install Python separately. **git** downloads the
code and its updates. The repository is private, so you must be signed in
to a GitHub account with access. Git asks you to sign in the first time.

### Windows 10 or 11

1. Open **PowerShell** (Start menu, type "PowerShell").
2. Install uv and git:
   ```powershell
   winget install --id=astral-sh.uv -e
   winget install --id=Git.Git -e
   ```
3. Close PowerShell and open it again, so it finds the new tools.
4. Download and start the game:
   ```powershell
   git clone https://github.com/Carbonpoint/botc-automod.git
   cd botc-automod
   uv run botc-automod
   ```
5. The first time, Windows Defender Firewall asks about Python. Allow it
   on **Private networks**. Your Wi-Fi must be set as a *Private* network
   (Settings > Network & internet > Wi-Fi > your network).

No winget? Install uv with
`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
and git from https://git-scm.com/download/win.

### macOS

1. Open **Terminal** (Applications > Utilities).
2. Install git (it comes with Apple's command-line tools) and uv:
   ```sh
   xcode-select --install
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Close Terminal and open it again.
4. Download and start the game:
   ```sh
   git clone https://github.com/Carbonpoint/botc-automod.git
   cd botc-automod
   uv run botc-automod
   ```
5. If macOS asks whether Python may accept incoming connections, click
   **Allow**.

### Linux

1. Install git with your package manager, then uv:
   ```sh
   sudo apt install git        # Debian, Ubuntu
   sudo dnf install git        # Fedora
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Open a new terminal, then:
   ```sh
   git clone https://github.com/Carbonpoint/botc-automod.git
   cd botc-automod
   uv run botc-automod
   ```
3. If phones cannot connect, open the port:
   `sudo ufw allow 8000/tcp` (Ubuntu) or
   `sudo firewall-cmd --add-port=8000/tcp --permanent && sudo firewall-cmd --reload` (Fedora).

### Updating

In the `botc-automod` folder, run `git pull`, then start the game again.

## Docker

The image holds everything, including Python. Build it once in the
project folder, then run it:

```sh
docker build -t botc-automod .
docker run -d --name botc -p 8000:8000 -v botc-data:/data \
  -e BOTC_PUBLIC_URL=http://192.168.1.20:8000/ botc-automod
```

Or with Compose (`compose.yaml` is in the project):

```sh
BOTC_PUBLIC_URL=http://192.168.1.20:8000/ docker compose up -d --build
docker compose logs      # shows the join address and QR code
```

Replace `192.168.1.20` with your computer's address on the home
network. A container cannot see that address by itself, and the QR code
uses it. Games, karma, settings and downloaded models live in the
`botc-data` volume. The Artist model is set with environment variables
(see [Artist question model](#artist-question-model)); `compose.yaml`
lists them. Podman runs the same files (`podman build`, `podman run`).

## Android host app

The `android/` folder builds **Clocktower Host**, an app that runs the game
server on an Android phone (Android 8 or newer, 64-bit). The host taps
*Turn the server on*; the app shows the QR code and address, and *Open the
game in my browser* takes the host into the game like everyone else. The
server keeps running in the background (a notification with a Stop
button), so the host can play in the browser on the same phone. Players
join on the same Wi-Fi, or on the phone's own hotspot.

The server is the same Python code as on a computer, run by Chaquopy.
The app's *Artist questions* section offers the same choices as the
desktop: no model, the packaged model on the phone (llama.cpp is built
into the app), an Ollama server on the network, or a cloud service with
an API key.

**Install on a phone:** copy `app-debug.apk` to the phone, open it, and
allow installs from that source when Android asks. Or, with USB debugging
on: `adb install app-debug.apk`.

**Build the APK** (Linux or macOS):

1. Install JDK 21 and the Android command-line tools; with `sdkmanager`
   install `platform-tools`, `platforms;android-36` and (optional, to strip
   native libraries) an `ndk`.
2. Have a Python 3.12 on the build machine (`uv python install 3.12`) and
   point `BOTC_BUILD_PYTHON` at it.
3. Build:
   ```sh
   cd android
   echo "sdk.dir=$HOME/android-sdk" > local.properties
   ./fetch_llama.sh                 # llama.cpp for the packaged model (about 26 MB)
   BOTC_BUILD_PYTHON=$(uv python find 3.12) ./gradlew assembleDebug
   ```
   The APK is `app/build/outputs/apk/debug/app-debug.apk` (about 34 MB).

## Artist question model

The Artist asks the Storyteller any yes/no question. An automated
storyteller needs a language model to read it. The model only
translates the question into a small query (`artist/query.py`). The
game engine then answers the query from the true game state, so the
model can misread a question but cannot give a false answer. The Artist
sees the reading ("I understood: Kofi is evil?") and confirms it before
the ability is used.

The first time the server starts, it asks which model to use:

| Choice | What you need |
|---|---|
| No model | Nothing. The Artist is dealt only when a human storyteller runs the game. |
| Local: packaged model | Nothing. It downloads llama.cpp (about 20 MB) and the model once, then runs on the CPU. |
| Local: Ollama | An Ollama server. You give its address and pick a model from its list. |
| Cloud | A provider (Anthropic, OpenAI, Google Gemini, OpenRouter, or any OpenAI-compatible server), an API key, and a model name. |

The choice is saved in the settings file (`~/.config/botc-automod/config.json`,
readable only by you, because it can hold an API key). Run
`botc-automod --setup` to change it. The server tests the model with a
sample question at every start; if it fails, the game runs without it.
API keys are asked in the terminal, never on the web page. The Anthropic
backend needs the cloud extra: `uv run --extra cloud botc-automod`.
With the default model (`claude-opus-5`), it turns on Anthropic's
server-side fallback, which retries a declined request on another model.

Environment variables override the file (for Docker):
`BOTC_ARTIST` (`none`, `packaged`, `ollama`, `anthropic`, `openai`,
`gemini`, `openrouter`, `custom`), `BOTC_ARTIST_URL`, `BOTC_ARTIST_MODEL`,
`BOTC_ARTIST_KEY`.

## Options

| Option | Default | What it does |
|---|---|---|
| Demon bluffs in small games | on | The Demon learns 3 good characters that are not in play, even with 5 or 6 players. Off follows the official rule (no evil info below 7 players). The bluffs also stay on the Demon's Me tab. |
| Karma | on | A right answer to the night question gives +1 karma, a wrong one -1. Karma is kept per name across games on this server (`karma.json` in the data folder). |

Karma tilts the automod's chance decisions a little: a player's "favour"
is 1 + 0.15 x karma, kept between 0.4 and 2.5. High favour makes bad
random outcomes less likely (being the drunk one of the Innkeeper's pair,
the Gossip or Mayor victim, the Sweetheart's drunk, the Tinker's death)
and good ones more likely (a Pacifist save, a Shabaloth return). It also
gives a player's team and style wishes more weight in the deal.

## Automated storyteller decisions

A human storyteller makes judgement calls. The automod uses these rules.
The chances are host settings.

| Decision | Rule |
|---|---|
| Drunk or poisoned info | A random answer that differs from the true one |
| Spy / Recluse registration | Registers falsely with chance `misregister` (0.35), once per player per night or day. A false registration can add a false match but never hides the true one: a lone Recluse is still found by the Librarian, a lone Spy by the Investigator |
| Mayor killed at night | Another killable player dies instead with chance `mayor_bounce` (0.5) |
| Imp kills itself | The Scarlet Woman takes over if 5+ were alive; else a random living Minion |
| Sailor | A chosen Townsfolk gets drunk; otherwise the Sailor does |
| Innkeeper | One of the two players, at random, is drunk |
| Gossip | Statements are built from a menu. A true one kills a random killable living player that night |
| Tinker | Dies at night with chance `tinker_chance` (0.1) |
| Pacifist | An executed good player survives with chance `pacifist_save` (0.5) |
| Shabaloth | Brings back last night's victim with chance `shabaloth_regurgitate` (0.3) |
| Godfather | The Outsider change (-1 or +1) is random |
| Savant | Two generated statements about the game, one true and one false |
| Artist | Dealt only if a question model is set up (see [Artist question model](#artist-question-model)) |
| Pit-Hag makes a Demon | No extra deaths |
| Sweetheart | A random other living player becomes drunk for the rest of the game |
| Vigormortis | Which of the two Townsfolk neighbours is poisoned is random |
| Mutant, Cerenovus | Not dealt: judging "madness" needs a human storyteller |
| Karma | Chance decisions above are tilted by karma (see Options) |

## Human storyteller tools

The Grimoire tab shows every character, alignment and reminder (drunk or
poisoned, protected, cursed, mad, gained abilities). The storyteller can:
change any character; kill or revive a player; send a private message;
execute a player now (for madness; it is the day's execution); answer
Artist and Savant requests; edit or add night messages before they go
out; declare a winner. The Characters tab shows the official "How to Run"
notes for each character.

## Layout

| Path | What |
|---|---|
| `src/botc_automod/game.py` | Engine: lobby, phases, timers, nominations, votes, per-player views |
| `src/botc_automod/editions/rules.py` | Shared rules: statuses, deaths and protection, night order, day actions, wins |
| `src/botc_automod/editions/chars_tb.py` | Trouble Brewing characters (also `chars_bmr.py`, `chars_snv.py`) |
| `src/botc_automod/editions/trouble_brewing.py` | An edition: its characters and night orders (also `bad_moon_rising.py`, `sects_and_violets.py`) |
| `src/botc_automod/editions/data/*.json` | Character text from the official wiki |
| `src/botc_automod/assign.py` | The preference-aware deal |
| `src/botc_automod/seating.py` | Room shapes to seat positions |
| `src/botc_automod/decoys.py` | Decoy night questions |
| `src/botc_automod/server.py` | FastAPI HTTP + WebSocket server, save and reload |
| `src/botc_automod/static/` | The phone web app (plain HTML, CSS, JS) |
| `tests/` | Rule tests, random full games in all editions and both modes, and the info audit |
| `src/botc_automod/audit.py` | Independent checker: is every piece of night info accurate, complete and delivered? |
| `scripts/audit_info.py` | Runs many automod games through the checker and reports problems |
| `scripts/rejoin_check.py` | Browser check of reload, rejoin in the lobby, and approved rejoin in a game |
| `docs/artist-llm.md` | Plan for a small local LLM to answer the Artist |
| `scripts/fetch_wiki.py` | Refetches character text from the wiki |
| `scripts/smoke.py` | 7 WebSocket bots play night 1 against a running server |
| `scripts/ui_check.py` | Headless phone browsers play to a vote and save screenshots |

## Add a character or an edition

A character is a `Char` subclass in a `chars_*.py` file. It overrides only
the hooks it needs: `task` (its night prompt), `resolve` (its effect, run
in night order), `on_death`, `day_action` or `public_action`, and hooks
such as `on_nominate` or `after_execution`. An edition is a
`ScriptEdition` with a character list and two night orders. Register it
in `editions/__init__.py`. Night orders come from the official night
sheet.

## Tests

```sh
uv run pytest -q
```

Blood on the Clocktower is a game by The Pandemonium Institute. Character
text comes from the official wiki (wiki.bloodontheclocktower.com). This
project is a private, unofficial tool for playing at home.
