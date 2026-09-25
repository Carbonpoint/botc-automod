# botc-automod

A self-hosted server for playing Blood on the Clocktower at home, with an
automated storyteller. Everyone sits in the same room and plays on their
phone's web browser. One player hosts, but the host is also a player and
learns nothing secret.

Edition so far: **Trouble Brewing** (5 to 15 players). The engine is built
so that other editions can be added as new files in `editions/`.

## Run it

```sh
cd ~/botc-automod
uv run botc-automod              # listens on all addresses, port 8000
uv run botc-automod --port 8080  # another port
```

It prints the address players open, for example `http://10.27.64.202:8000`.
Phones must be on the same network. On Fedora, firewalld may block the
port for other devices; opening it needs root
(`firewall-cmd --add-port=8000/tcp`).

Games are saved to `~/.local/share/botc-automod/` after every change and
reload when the server restarts. Set `BOTC_DATA` to save elsewhere.
Set `BOTC_DEBUG=1` to enable `/api/debug/{code}`, which shows the full
Grimoire. Never enable it during a real game.

## How a game goes

1. **Lobby.** One player taps *Host a new game*. The host screen shows a
   QR code and a 4-letter code. Others open the page and join.
2. **Room.** The host picks the room shape: circle, horseshoe, square, or
   grid. For a grid, the host sets rows and columns and taps the seat
   squares in clockwise order. Each player taps their own seat. Seat order
   matters: the Chef and the Empath use neighbours.
3. **Preferences.** Each player picks a team (good, evil, no preference)
   and a style (chill, thinking, no preference). The deal is random but
   honours these where it can: team first, then style.
4. **Nights.** Every phone gets a task, so nobody can tell who acts.
   Characters with a night action choose players. Everyone else gets a
   quick maths or trivia question. Each night has two stages:
   - Stage A: all choices (Poisoner, Monk, Imp, Fortune Teller, Butler)
     and, with 7+ players, the evil team's info and the Demon's bluffs.
   - Stage B: information (Washerwoman, Chef, Empath, Undertaker, Spy...)
     and the Ravenkeeper, if the Demon killed them.
   A stage ends when everyone is done (after at least `night_min` seconds),
   or at `night_max`, when unanswered choices are made at random.
5. **Days.** Discussion, then nominations. A nominator taps a player; the
   town hears the accusation and defence; everyone votes on their phone.
   Dead players have one ghost vote. The player with the most votes (at
   least half the living, and no tie) is executed at the end of the day.
   Anyone can claim a Slayer shot from the Town screen; only the real
   Slayer's shot can kill.
6. **Host.** The host's *Host* tab shows lines to read aloud (only public
   facts), timer controls (pause, add or remove time, move on now),
   default times, and the storyteller chances below.
7. **End.** When a team wins, every phone shows the full Grimoire.

## Storyteller decisions

A human storyteller makes judgement calls. The automod uses these rules:

| Decision | Rule |
|---|---|
| Spy / Recluse registration | Registers falsely with chance `misregister` (default 0.35), once per player per night or day |
| Mayor killed at night | Another killable player dies instead with chance `mayor_bounce` (default 0.5) |
| Drunk or poisoned info | A random answer that differs from the true one |
| Imp kills itself | The Scarlet Woman takes over if 5+ were alive; else a random living Minion |
| Fortune Teller red herring | A random good player, picked at setup |
| Demon bluffs | 3 Townsfolk not in play, never the Drunk's fake character |

## Layout

| Path | What |
|---|---|
| `src/botc_automod/game.py` | Engine: lobby, phases, timers, nominations, votes, per-player views |
| `src/botc_automod/editions/base.py` | The interface an edition implements |
| `src/botc_automod/editions/trouble_brewing.py` | All 22 characters, setup table, night order, abilities, win rules |
| `src/botc_automod/assign.py` | The preference-aware deal |
| `src/botc_automod/seating.py` | Room shapes to seat positions |
| `src/botc_automod/decoys.py` | Decoy night questions |
| `src/botc_automod/server.py` | FastAPI HTTP + WebSocket server, save and reload |
| `src/botc_automod/static/` | The phone web app (plain HTML, CSS, JS) |
| `tests/test_engine.py` | Rules tests plus 40 random full games |
| `scripts/smoke.py` | 7 WebSocket bots play night 1 against a running server |
| `scripts/ui_check.py` | 5 headless phone browsers play to a vote and save screenshots |

## Add an edition

Subclass `Edition` in a new file under `editions/`, fill in `roles`,
`setup`, `stage_a`, `resolve_a`, `resolve_b` and `check_win`, and override
the day hooks you need. Register it in `editions/__init__.py`.

## Tests

```sh
uv run pytest -q
```

Blood on the Clocktower is a game by The Pandemonium Institute. Character
ability text follows the official almanac wording. This project is a
private, unofficial tool for playing at home.
