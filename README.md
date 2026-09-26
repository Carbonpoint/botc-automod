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

## Run it

```sh
cd ~/botc-automod
uv run botc-automod              # listens on all addresses, port 8000
uv run botc-automod --port 8080  # another port
uv run botc-automod --no-qr      # skip the terminal QR code
```

The server prints the join address and a QR code in the terminal.
Players scan it or type the address. The host's lobby screen shows the
same QR code. Phones must be on the same network. On Fedora, firewalld
may block the port for other devices. Opening it needs root
(`firewall-cmd --add-port=8000/tcp`).

Games are saved to `~/.local/share/botc-automod/` after every change and
reload when the server restarts. Set `BOTC_DATA` to save elsewhere.
Saves from an older format are skipped. Set `BOTC_DEBUG=1` to enable
`/api/debug/{code}`, which shows the full Grimoire. Never enable it
during a real game.

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
| Artist | Not dealt: it needs a human storyteller for now (plan: docs/artist-llm.md) |
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
