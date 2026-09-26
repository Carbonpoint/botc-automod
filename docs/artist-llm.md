# A small local LLM for the Artist

Status: plan only. The Artist is dealt only with a human storyteller until
this exists.

## The idea: the model translates, the engine answers

The Artist asks "any yes/no question" and must get a true answer. A small
model that answers from its own reading of the game will sometimes be
wrong, and a wrong answer breaks the game. So the model never decides the
answer. It only translates the question into a small query language. The
engine then evaluates the query against the true game state.

```
"Is the guy next to me evil?"
    -> model -> {"q": "is_alignment", "player": "seat_left_of:Jess", "team": "evil"}
    -> engine -> true -> "Yes."
```

If the model's output does not parse, or the question is outside the
language ("Will good win?"), the Artist hears "Please ask a different
question" and keeps their ability. The page also echoes the model's
reading ("I understood: Is Kofi evil?"), so the player can catch a
misunderstanding before the answer counts.

With this split, a wrong answer can only come from a wrong translation
that still parses. Constrained decoding (a JSON schema or GBNF grammar in
llama.cpp) makes every output parse, so the risk moves to picking the
wrong query. That risk is what we measure.

The model needs only the player names and the character list, never the
Grimoire, so it cannot leak secrets.

## The query language (first draft)

| Query | Example question |
|---|---|
| `is_role(player, character)` | Is Ann the Fortune Teller? |
| `is_type(player, type)` | Is Ben a Minion? |
| `is_alignment(player, team)` | Is Cat evil? |
| `in_play(character)` | Is the Vortox in play? |
| `any_of(players, predicate)` | Is the Demon one of Ann, Ben or Cat? |
| `count(predicate) op n` | Are there 2 or more evil players alive? |
| `was_malfunctioning(player, day)` | Was Dan drunk or poisoned yesterday? |
| `voted(player, day)`, `nominated(player, day)` | Did a Minion nominate today? |
| seat references | "my left neighbour", "the player opposite me" |

The engine already evaluates the first four (`statement_true` in
`editions/rules.py`). The rest are small additions.

## Which model

Candidates, smallest first (check for newer releases before starting;
this list is from mid-2026): Qwen3 0.6B and 1.7B, Gemma 3 1B, Llama 3.2
1B, SmolLM 1.7B/3B, then Qwen3 4B, Phi-4-mini and Gemma 3 4B.

Expectation: with grammar-constrained output, a 1.5 to 2B model should
parse most plain questions. A 0.6B model probably needs fine-tuning. At
4-bit quantisation a 1.7B model needs about 1.2 GB of RAM and answers in a
few seconds on a laptop CPU, which is fine for an ability used once per
game. The lab already has llama.cpp servers that fit (the hub Arc A750,
and Ollama on stalker).

## How to choose: a benchmark first

1. Generate game states from the simulator (names, seats, characters).
2. For each state, write questions from templates, and have a large
   model paraphrase them into casual table talk ("is the lady across
   from me sus?"). Label each with its gold query. Label unanswerable
   questions as "ask another".
3. Execute every gold query against its state, so labels are checked by
   the engine, not by trust.
4. Score each candidate model on: exact query match; **wrong-answer
   rate** (a parsed query whose truth differs from the gold query's
   truth); and refusal rate on answerable questions.
5. Pick the smallest model with a wrong-answer rate near 0 (target below
   0.5%) and an acceptable refusal rate.

## Distilling a purpose-built model

If no small model passes, fine-tune one (LoRA on a 0.5B to 1.7B base).

- Training pairs: (question + names + character list) -> query, produced
  as in the benchmark, at a scale of 10k to 50k pairs.
- The wiki helps with vocabulary: character names, and table slang such
  as "ping", "registers", "3-for-3" and "outed". The model does not need
  to learn game strategy, because it only translates.
- Simulated games supply realistic contexts and let the engine verify
  every label. Their outcomes are not needed as training targets.
- Keep a held-out set of human-written questions from real games; it is
  the honest test.

The same translator could later judge free-text Gossip statements and
build Savant statements.
