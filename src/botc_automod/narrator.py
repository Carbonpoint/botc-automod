"""Morning stories for the narrator: a twisted tale of how each victim died.

The story contains no secret. The only true facts are the names of the
players who died. Every other name in it is picked at random from the
living players, with its own random source, so a name in a story never
says anything about a character or a team. Players are "they" throughout.
"""

from __future__ import annotations

import random

_rng = random.SystemRandom()

OPENINGS = [
    "The snow fell thick on Ravenswood Bluff, and the clocktower struck three.",
    "A cold fog rolled in from the river and swallowed every lantern in town.",
    "The moon hid behind the clocktower, as if it did not want to watch.",
    "Somewhere a dog howled, and then, very suddenly, it stopped.",
    "The wind rattled every shutter in Ravenswood Bluff, one after another.",
    "The town slept. Well, most of the town slept.",
]

# {w1} and {w2} are two random living players; {h} is a random living player (the red herring).
SETUPS = [
    "{w1} could not sleep, so they set off through the snow to visit {w2}.",
    "{w1} and {w2} were walking home from the tavern, arguing about the price of turnips.",
    "{w1} crept out to return a book that {w2} had lent them three years ago.",
    "{w1} went looking for their lost cat, and {w2} came along with a lantern.",
    "{w1} woke {w2} at midnight, sure they had heard footsteps on the roof.",
    "{w1} and {w2} had agreed to meet at the well to share a secret.",
]

HERRINGS = [
    "On their way, they heard a blood-curdling scream from {h}'s house. They burst in, and found that {h} had burned their crepes.",
    "They passed {h}'s cellar and saw a strange green glow. It was only {h}, brewing a very suspicious soup.",
    "A shadow darted across the square. It was {h}, in their nightgown, chasing a runaway goose.",
    "They heard digging behind {h}'s cottage. {h} said they were planting turnips. At midnight. In the snow.",
    "From {h}'s window came an awful screeching. {h} was practising the violin, badly, again.",
    "They found {h} standing very still in the graveyard. {h} said they were counting the stars.",
    "Someone was sharpening a knife in {h}'s kitchen. {h} said it was for the cheese. Nobody asked which cheese.",
    "{h}'s door was wide open and the house was empty, but the kettle was still warm.",
]

DEATHS = [
    "But on their way out, they saw red drops in the snow. They followed them to {v}, who stood up, whispered \"it was...\", and dropped dead on the spot.",
    "Then the church bell rang once, all by itself. When they looked up, {v} was hanging from the bell rope, cold as the snow.",
    "Then they found {v} slumped by the well, with a look of great surprise on their face, and nothing else going for them.",
    "At the edge of the woods they found {v}'s lantern, still burning. A little further on, they found {v}. Not still burning. Not anything, anymore.",
    "Then a door creaked. {v} stepped out, pale as milk, said \"I don't feel so well,\" and fell face down in the snow, dead.",
    "By the clocktower, they found {v} lying in a perfect circle of black feathers. {v} would not be getting up again.",
    "They knocked on {v}'s door. It swung open. {v} sat at the table, dinner untouched, eyes open, and very, very dead.",
    "In the town square the snow was melting in one small patch. Under it lay {v}, who had seen their last sunrise yesterday.",
]

MORE_DEATHS = [
    "And that was not all.",
    "But the night was not finished with Ravenswood Bluff.",
    "Before anyone could scream, there was worse news.",
]

QUIET = [
    "They searched the whole town, knocking on every door, and every door opened. Everyone was alive. For now.",
    "They waited for a scream that never came. Nobody died last night. Somebody, somewhere, is disappointed.",
    "At dawn they counted every face in the square. Not one was missing. The Demon, it seems, stayed in bed.",
]

FIRST_NIGHT = [
    "Strangers have come to Ravenswood Bluff, and among them walks a Demon.",
    "New faces arrived in Ravenswood Bluff today. One of them is not what they seem.",
    "Tonight is the first night. The Demon has only just unpacked.",
]

FIRST_NIGHT_ENDS = [
    "Nobody died on this first night. The Demon was only getting to know the neighbours.",
    "By morning, everyone was alive. Everyone was also lying about something.",
    "Nobody died. But everybody is now a suspect.",
]

CLOSINGS = [
    "The sun rises. Someone in this town knows exactly what happened.",
    "Wake up, Ravenswood Bluff. There is a murderer among you.",
    "Morning has come. Now: who did it?",
    "The bells ring for a new day. Keep your friends close.",
]


# Jo Jo's Mid-Autumn Festival: a party in Jo Jo's apartment in Ames, Iowa,
# on a dreary, cold, rainy fall night. The moon is somewhere behind the rain.
JOJO_OPENINGS = [
    "Rain hammered the windows of Jo Jo's apartment in Ames, and the full moon hid behind the clouds, sulking.",
    "It was a cold, wet Mid-Autumn night in Ames, Iowa. The paper lanterns on Jo Jo's balcony dripped and swayed.",
    "Somewhere down Lincoln Way a CyRide bus hissed through the puddles. Inside Jo Jo's apartment, the mooncakes waited.",
    "The radiator in Jo Jo's apartment clanked twice, then gave up. The rain did not give up at all.",
    "Wet leaves stuck to every window. The cornfields beyond Ames were black, and the moon would not come out.",
    "Jo Jo lit another lantern. The rain blew it out. Jo Jo lit it again. It was that kind of night.",
]

JOJO_SETUPS = [
    "{w1} could not sleep on Jo Jo's couch, so they went to the kitchen with {w2} to steal one more mooncake.",
    "{w1} and {w2} stepped out onto the balcony, hoping the clouds would part and show them the moon.",
    "{w1} dragged {w2} down to the laundry room, because someone had put a wet coat in the dryer with their phone in it.",
    "{w1} and {w2} ran through the rain to the Hy-Vee on Lincoln Way, because Jo Jo had run out of tea.",
    "{w1} woke {w2} to tell them that the salted egg yolk mooncakes were missing. All of them.",
    "{w1} and {w2} carried the last paper lantern down the stairwell, arguing about the story of Chang'e and the rabbit.",
]

JOJO_HERRINGS = [
    "From the bathroom came a terrible scream. It was {h}, who had bitten into a lotus-seed mooncake and found a whole egg yolk.",
    "They found {h} on the balcony in the pouring rain, howling at the clouds where the moon should be.",
    "{h} was in the kitchen with a very large knife. {h} said it was for the pomelo. Nobody had seen a pomelo all night.",
    "The smoke alarm went off. It was {h}, who had tried to toast a mooncake in Jo Jo's toaster.",
    "They heard digging in the flower pots by the door. It was {h}, burying the five-nut mooncakes so nobody would have to eat them.",
    "{h} stood alone in the parking lot, soaked to the bone, holding a lantern shaped like a rabbit. {h} said they were waiting for a ride.",
    "{h} was on the phone in the stairwell, whispering. When they came closer, {h} hung up and said it was their mother.",
    "Every light in the apartment flickered. In the dark, they saw {h} holding the fuse box door, smiling.",
]

JOJO_DEATHS = [
    "But on their way back, they slipped on something wet by the door. It was not rain. It was {v}, face down on Jo Jo's doormat, and very, very dead.",
    "Then a lantern floated past the window, all by itself. Under the balcony, in the puddles, lay {v}. The rain kept falling on them.",
    "In the kitchen they found {v} at the table, a half-eaten mooncake in their hand, cold as the Iowa rain. They had eaten their last one.",
    "The dryer stopped. When they opened it, {v} was not inside, thankfully. {v} was behind it, and not breathing.",
    "Outside, on the flooded sidewalk, a paper lantern drifted in a circle around {v}, who would not see the moon this year, or ever again.",
    "The clouds parted for one moment. In the moonlight they saw {v} lying across the stairs, as still as the rabbit on the moon.",
    "They found {v} on Jo Jo's couch, wrapped in a blanket, eyes open, staring at the ceiling fan. It was still spinning. {v} was not.",
    "At the bottom of the stairwell, under the flickering exit sign, lay {v}. Their umbrella was still open. It did not help.",
]

JOJO_MORE_DEATHS = [
    "And the rain was not done with Jo Jo's party.",
    "But before anyone could call 911, there was more.",
    "Then Jo Jo screamed from the other room.",
]

JOJO_QUIET = [
    "They searched every room in Jo Jo's apartment. Everyone was alive, damp, and grumpy. For now.",
    "They waited for a scream, but all they heard was the rain. Nobody died. The mooncakes were not so lucky.",
    "At dawn they counted every guest at Jo Jo's party. Nobody was missing. The Demon must have hated the rain too.",
]

JOJO_FIRST_NIGHT = [
    "Jo Jo invited everyone over to celebrate the Mid-Autumn Festival. One of his guests is a Demon.",
    "The guests arrived at Jo Jo's apartment with wet shoes, mooncakes and secrets. Mostly secrets.",
    "Tonight is the first night of the party. Somebody did not come for the mooncakes.",
]

JOJO_FIRST_NIGHT_ENDS = [
    "Nobody died on this first night. The Demon was only choosing their favourite mooncake.",
    "By morning, everyone was alive. Everyone also had a very good reason to be in the kitchen.",
    "Nobody died. But nobody at Jo Jo's party is above suspicion.",
]

JOJO_CLOSINGS = [
    "Grey morning light creeps over Ames. Somebody at this party knows exactly what happened.",
    "The rain keeps falling. There is a murderer among Jo Jo's guests.",
    "Morning has come to Ames, Iowa. Now: who did it?",
    "Jo Jo puts the kettle on. Keep your friends close, and your mooncakes closer.",
]

THEMES = {
    "default": {"name": "Default", "openings": OPENINGS, "setups": SETUPS, "herrings": HERRINGS,
                "deaths": DEATHS, "more_deaths": MORE_DEATHS, "quiet": QUIET, "first_night": FIRST_NIGHT,
                "first_night_ends": FIRST_NIGHT_ENDS, "closings": CLOSINGS},
    "jojo": {"name": "Jo Jo's Mid-Autumn Festival", "openings": JOJO_OPENINGS, "setups": JOJO_SETUPS,
             "herrings": JOJO_HERRINGS, "deaths": JOJO_DEATHS, "more_deaths": JOJO_MORE_DEATHS,
             "quiet": JOJO_QUIET, "first_night": JOJO_FIRST_NIGHT, "first_night_ends": JOJO_FIRST_NIGHT_ENDS,
             "closings": JOJO_CLOSINGS},
}


def story(deaths: list[str], living: list[str], night: int, theme: str = "default") -> list[str]:
    """Paragraphs for the narrator to read aloud. `deaths` are tonight's victims."""
    t = THEMES.get(theme, THEMES["default"])
    pool = [n for n in living if n not in deaths] or list(living) or ["a stranger"]
    decks: dict[str, list[str]] = {}

    def draw(kind: str) -> str:
        """A random line; no line comes twice in one story."""
        deck = decks.setdefault(kind, [])
        if not deck:
            deck.extend(_rng.sample(t[kind], len(t[kind])))
        return deck.pop()

    def scene() -> list[str]:
        w1, w2, h = (_rng.sample(pool, 3) if len(pool) >= 3 else [_rng.choice(pool) for _ in range(3)])
        return [draw("setups").format(w1=w1, w2=w2), draw("herrings").format(h=h)]

    out = [draw("openings")]
    if not deaths:
        if night <= 1:
            out += [draw("first_night"), *scene(), draw("first_night_ends")]
        else:
            out += [*scene(), draw("quiet")]
    for i, v in enumerate(deaths):
        if i:
            out.append(draw("more_deaths"))
        out += [*scene(), draw("deaths").format(v=v)]
    out.append(draw("closings"))
    return out
