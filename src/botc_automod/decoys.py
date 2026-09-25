"""Decoy night tasks.

Players with nothing to do at night still get a task on their phone, so
nobody at the table can tell who is acting from who is holding a phone.
"""

import random

TRIVIA = [
    ("How many legs does a spider have?", "8", ["6", "10", "12"]),
    ("What colour do you get by mixing blue and yellow?", "Green", ["Purple", "Orange", "Brown"]),
    ("Which planet is closest to the Sun?", "Mercury", ["Venus", "Mars", "Earth"]),
    ("How many days are in a leap year?", "366", ["365", "364", "367"]),
    ("What is frozen water called?", "Ice", ["Steam", "Fog", "Dew"]),
    ("How many sides does a hexagon have?", "6", ["5", "7", "8"]),
    ("Which animal is known as the king of the jungle?", "Lion", ["Tiger", "Bear", "Wolf"]),
    ("What is the largest ocean on Earth?", "Pacific", ["Atlantic", "Indian", "Arctic"]),
    ("How many minutes are in an hour?", "60", ["100", "30", "90"]),
    ("Which bird is a symbol of peace?", "Dove", ["Crow", "Eagle", "Owl"]),
    ("What do bees make?", "Honey", ["Milk", "Silk", "Wax paper"]),
    ("How many strings does a standard guitar have?", "6", ["4", "5", "8"]),
    ("Which season comes after winter?", "Spring", ["Summer", "Autumn", "Winter"]),
    ("What is the chemical symbol for gold?", "Au", ["Ag", "Go", "Gd"]),
    ("How many continents are there?", "7", ["5", "6", "8"]),
    ("Which instrument has 88 keys?", "Piano", ["Violin", "Flute", "Harp"]),
    ("What gas do plants take in?", "Carbon dioxide", ["Oxygen", "Helium", "Neon"]),
    ("How many hours are in a day?", "24", ["12", "20", "36"]),
    ("Which shape has three sides?", "Triangle", ["Square", "Circle", "Pentagon"]),
    ("What is the tallest animal?", "Giraffe", ["Elephant", "Horse", "Camel"]),
    ("Which metal is liquid at room temperature?", "Mercury", ["Iron", "Tin", "Lead"]),
    ("How many players are on a football (soccer) team on the field?", "11", ["9", "10", "12"]),
    ("What is the opposite of 'north'?", "South", ["East", "West", "Up"]),
    ("Which fruit keeps the doctor away, says the proverb?", "Apple", ["Banana", "Pear", "Grape"]),
    ("How many wheels does a tricycle have?", "3", ["2", "4", "1"]),
    ("Which card suit is shaped like a heart?", "Hearts", ["Spades", "Clubs", "Diamonds"]),
    ("What is the boiling point of water in Celsius at sea level?", "100", ["90", "80", "120"]),
    ("Which month has the fewest days?", "February", ["April", "June", "November"]),
    ("What is a baby cat called?", "Kitten", ["Puppy", "Cub", "Foal"]),
    ("How many colours are in a rainbow?", "7", ["5", "6", "8"]),
]


def _math(rng: random.Random) -> tuple[str, str, list[str]]:
    kind = rng.choice(["+", "-", "x"])
    if kind == "+":
        a, b = rng.randint(3, 40), rng.randint(3, 40)
        ans = a + b
    elif kind == "-":
        a, b = rng.randint(20, 60), rng.randint(2, 19)
        ans = a - b
    else:
        a, b = rng.randint(2, 9), rng.randint(2, 9)
        ans = a * b
    wrong: set[int] = set()
    while len(wrong) < 3:
        w = ans + rng.choice([-10, -2, -1, 1, 2, 10])
        if w != ans and w >= 0:
            wrong.add(w)
    return f"What is {a} {kind} {b}?", str(ans), [str(w) for w in wrong]


def decoy_task(rng: random.Random) -> dict:
    """A tap-to-answer question. The answer does not matter to the game."""
    if rng.random() < 0.5:
        q, right, wrong = _math(rng)
    else:
        q, right, wrong = rng.choice(TRIVIA)
    options = [right, *wrong]
    rng.shuffle(options)
    return {
        "kind": "decoy",
        "title": "Night task",
        "text": q,
        "options": options,
        "answer": right,
    }
