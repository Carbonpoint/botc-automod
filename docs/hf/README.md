---
license: apache-2.0
base_model: HuggingFaceTB/SmolLM2-360M-Instruct
tags: [gguf, blood-on-the-clocktower, structured-output]
---

# botc-automod Artist translator

A 360M-parameter model, fine-tuned from SmolLM2-360M-Instruct, that
translates a player's yes/no question in *Blood on the Clocktower* into one
query in a small JSON language. It is used by
[botc-automod](https://github.com/Carbonpoint/botc-automod) when the
automated storyteller answers the **Artist**.

The model does not answer questions. The game engine evaluates the query
against the true game state, and the player confirms the engine's
plain-English reading before the answer is given. A misread question can
be rephrased; it cannot produce a false answer without the player seeing
the reading first.

## Input and output

System prompt: `Translate the Blood on the Clocktower yes/no question into a JSON query.`

User message:

```
Players (clockwise): Ann, Ben, Cat, Dan, Eve
Asker: Ann
Characters: chef=Chef, imp=Imp, ...
Question: is the person on my left evil?
```

Output: `{"query":{"op":"is_team","player":"cw:me","team":"evil"}}`, or
`{"query":{"op":"unanswerable"}}` for questions that are not yes/no about
the current game.

## Training

LoRA (rank 64, all linear layers), 30,000 generated examples, 2 epochs,
learning rate 2e-4. Examples pair random game worlds (3,288 real and
invented player names, all three base editions) with templated questions
and augmentation (typos, chatty openings, table talk). About 12% of
questions are unanswerable.

## Evaluation

| Set | Right | Misread | Refused |
|---|---|---|---|
| Generated test (300; unseen wording and names) | 91.3% | 6.7% | 2.0% |
| Hand-written (103; casual, typos, 20 unanswerable) | 95.1% | 3.9% | 1.0% |

8-bit GGUF with llama.cpp on a 4-core CPU; 0.8 to 2 seconds per question.
The 4-bit file scores 89.7% and 93.2%. Some hand-written failure patterns
informed later training templates (not the questions themselves), so the
generated test set is the more independent measure.

## Files

- `botc-artist-q8.gguf`: 8-bit (Q8_0), 386 MB, for computers
- `botc-artist-q4.gguf`: 4-bit (Q4_K_M), 271 MB, for phones
- `SHA256SUMS`: checksums
