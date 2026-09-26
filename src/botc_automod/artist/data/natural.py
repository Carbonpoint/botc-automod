"""Hand-written questions: the honest held-out test.

Players in seat order (clockwise), Trouble Brewing: Morgan (the asker), Riley,
Jordan, Casey, Taylor, Avery, Skyler, Harper, Rowan, Emery. "My left" is the
next player clockwise. None of these names are in the training data.

Each entry: (question, gold query). Gold "U" means unanswerable.
"""

U = {"op": "unanswerable"}
PLAYERS = ["Morgan", "Riley", "Jordan", "Casey", "Taylor", "Avery", "Skyler", "Harper", "Rowan", "Emery"]
ASKER = "Morgan"


def role(p, r): return {"op": "is_role", "player": p, "role": r}
def typ(p, t): return {"op": "is_type", "player": p, "type": t}
def team(p, t): return {"op": "is_team", "player": p, "team": t}
def inplay(r): return {"op": "in_play", "role": r}
def malf(p): return {"op": "is_malfunctioning", "player": p}
def count(of, cmp, n, alive=False): return {"op": "count", "of": of, "alive_only": alive, "cmp": cmp, "n": n}
def OR(*a): return {"op": "or", "args": list(a)}
def AND(*a): return {"op": "and", "args": list(a)}
def NOT(a): return {"op": "not", "arg": a}


QUESTIONS = [
    ("is riley the imp", role("Riley", "imp")),
    ("Is Jordan actually the Chef like he said?", role("Jordan", "chef")),
    ("casey claimed empath yesterday. is that her real character?", role("Casey", "empath")),
    ("Is Taylor the drunk?", role("Taylor", "drunk")),
    ("am i the drunk", role("me", "drunk")),
    ("Is Avery the spy?", role("Avery", "spy")),
    ("Skyler says virgin. true?", role("Skyler", "virgin")),
    ("Is Harper our fortune teller", role("Harper", "fortuneteller")),
    ("is rowan the FT", role("Rowan", "fortuneteller")),
    ("Is Emery the scarlet woman?", role("Emery", "scarletwoman")),
    ("Is Riley the Baron?", role("Riley", "baron")),
    ("hmm, is jordan the poisoner?", role("Jordan", "poisoner")),
    ("Is Casey the real slayer", role("Casey", "slayer")),
    ("Taylor = mayor?", role("Taylor", "mayor")),
    ("Is Avery a minion?", typ("Avery", "minion")),
    ("Is Skyler the demon", typ("Skyler", "demon")),
    ("is harper an outsider", typ("Harper", "outsider")),
    ("Is Rowan a townsfolk?", typ("Rowan", "townsfolk")),
    ("Is Emery secretly a minion?", typ("Emery", "minion")),
    ("riley demon?", typ("Riley", "demon")),
    ("Is Jordan evil?", team("Jordan", "evil")),
    ("Is Casey good", team("Casey", "good")),
    ("can i trust taylor", team("Taylor", "good")),
    ("Is Avery on the evil team?", team("Avery", "evil")),
    ("is skyler one of the bad guys", team("Skyler", "evil")),
    ("Is Harper on my team? I'm good.", team("Harper", "good")),
    ("Am I evil?", team("me", "evil")),
    ("Is there a Baron in the game?", inplay("baron")),
    ("is the saint in play", inplay("saint")),
    ("Does anybody have the Recluse?", inplay("recluse")),
    ("Is there a soldier?", inplay("soldier")),
    ("Is the Scarlet Woman in this game?", inplay("scarletwoman")),
    ("any butler in play?", inplay("butler")),
    ("Is Rowan poisoned?", malf("Rowan")),
    ("is emery drunk or poisoned right now", malf("Emery")),
    ("Am I poisoned?", malf("me")),
    ("Is my information wrong because I'm drunk or poisoned?", malf("me")),
    ("Is Riley's ability not working (drunk/poisoned)?", malf("Riley")),
    ("Are there at least 2 outsiders?", count("outsider", ">=", 2)),
    ("are there exactly two outsiders", count("outsider", "==", 2)),
    ("Is there more than one minion?", count("minion", ">", 1)),
    ("Are 3 or more evil players still alive?", count("evil", ">=", 3, True)),
    ("Is the demon still alive?", count("demon", ">=", 1, True)),
    ("Are there zero outsiders?", count("outsider", "==", 0)),
    ("Are there fewer than 2 minions in the game?", count("minion", "<", 2)),
    ("Are at least 5 good players alive?", count("good", ">=", 5, True)),
    ("Is the demon Jordan or Casey?", OR(typ("Jordan", "demon"), typ("Casey", "demon"))),
    ("is either taylor or avery evil", OR(team("Taylor", "evil"), team("Avery", "evil"))),
    ("Is the demon one of Skyler, Harper or Rowan?",
     OR(typ("Skyler", "demon"), typ("Harper", "demon"), typ("Rowan", "demon"))),
    ("Is Riley or Jordan the Empath?", OR(role("Riley", "empath"), role("Jordan", "empath"))),
    ("Is Emery the spy or the recluse?", OR(role("Emery", "spy"), role("Emery", "recluse"))),
    ("Is Casey a minion or the demon?", OR(typ("Casey", "minion"), typ("Casey", "demon"))),
    ("Are both Taylor and Avery good?", AND(team("Taylor", "good"), team("Avery", "good"))),
    ("Are Skyler and Harper both evil?", AND(team("Skyler", "evil"), team("Harper", "evil"))),
    ("Is Rowan good and Emery evil?", AND(team("Rowan", "good"), team("Emery", "evil"))),
    ("Is Riley the chef and Jordan the empath?", AND(role("Riley", "chef"), role("Jordan", "empath"))),
    ("Is Casey not the demon?", NOT(typ("Casey", "demon"))),
    ("Is it true that Taylor is not evil?", NOT(team("Taylor", "evil"))),
    ("Is neither Avery nor Skyler the demon?", AND(NOT(typ("Avery", "demon")), NOT(typ("Skyler", "demon")))),
    ("Is the person on my left evil?", team("cw:me", "evil")),
    ("Is the player to my right good?", team("ccw:me", "good")),
    ("is my left neighbour the demon", typ("cw:me", "demon")),
    ("Is either of my neighbours evil?", OR(team("cw:me", "evil"), team("ccw:me", "evil"))),
    ("Am I sitting next to the demon?", OR(typ("cw:me", "demon"), typ("ccw:me", "demon"))),
    ("Is the player left of Casey a minion?", typ("cw:Casey", "minion")),
    ("Is Harper's right neighbour evil?", team("ccw:Harper", "evil")),
    ("Is the demon sitting next to Rowan?", OR(typ("cw:Rowan", "demon"), typ("ccw:Rowan", "demon"))),
    ("OK so here's my question: is Jordan the Imp? Yes or no.", role("Jordan", "imp")),
    ("Riley has been super quiet all game. Is Riley evil?", team("Riley", "evil")),
    ("I got pinged as the washerwoman's townsfolk. Anyway, is Casey the washerwoman?", role("Casey", "washerwoman")),
    ("Quick one - Taylor, demon, y/n?", typ("Taylor", "demon")),
    ("is avry evil", team("Avery", "evil")),
    ("Is skylar the undertaker", role("Skyler", "undertaker")),
    ("is harpr a minon", typ("Harper", "minion")),
    ("Is RoWaN the MONK?", role("Rowan", "monk")),
    ("Emery - ravenkeeper for real?", role("Emery", "ravenkeeper")),
    ("Is the imp in play", inplay("imp")),
    ("Does the Spy exist in this game?", inplay("spy")),
    ("Is Jordan the Investigator or the Librarian?", OR(role("Jordan", "investigator"), role("Jordan", "librarian"))),
    ("Is Casey telling the truth that she's good?", team("Casey", "good")),
    ("Is Avery lying about being good?", team("Avery", "evil")),
    ("Are there more than 3 evil players?", count("evil", ">", 3)),
    ("Is there exactly one outsider alive?", count("outsider", "==", 1, True)),
    ("Who is the demon?", U),
    ("What is Riley's character?", U),
    ("Which player is the spy?", U),
    ("Will the good team win?", U),
    ("Should I nominate Jordan today?", U),
    ("How many minions are in play?", U),
    ("What did Casey learn last night?", U),
    ("Who did the imp kill?", U),
    ("Is Taylor going to die tonight?", U),
    ("What's the best strategy for me?", U),
    ("Can you give me a clue?", U),
    ("Why did Avery vote for Skyler?", U),
    ("what time is it", U),
    ("Tell me the whole grimoire please", U),
    ("Which of my neighbours is evil?", U),
    ("How many players are drunk or poisoned?", U),
    ("Is it raining outside?", U),
    ("hello?", U),
    ("Who should I trust?", U),
    ("What character should I bluff as?", U),
]
