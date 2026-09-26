# A small language model for the Artist

## The design: the model translates, the engine answers

The Artist asks the Storyteller any yes/no question and must get a true
answer. A small model that answers from its own reading of the game would
sometimes be wrong. So the model never answers. It translates the question
into one query in a small language (`src/botc_automod/artist/query.py`), and
the game engine evaluates that query against the true game state.

```
"is the guy on my left evil?"
   -> model -> {"op": "is_team", "player": "cw:me", "team": "evil"}
   -> engine -> true -> "Yes."
```

Three guards keep a misread from costing the player:

1. **Structured output.** Every backend asks for JSON that fits a schema.
   The schema lists the real player names (plus `me`, `cw:NAME`,
   `ccw:NAME`), the real characters, the types and the teams, so the model
   cannot invent a name or a character.
2. **Validation.** Anything that does not parse or validate becomes "ask a
   different question", and the ability is not used.
3. **Confirmation.** The Artist sees the engine's plain reading ("I
   understood: the player on your left (Ben) is evil?") and must tap *Ask
   this*. A misread question can be rephrased at no cost.

The model only needs player names and the character list, never the
Grimoire, so it cannot leak secrets.

## The test sets

- **test** (300 questions): generated from templates the model never sees
  in training, with player names that never appear in training.
- **natural** (103 questions, `artist/data/natural.py`): written by hand,
  in casual table talk, with typos, nicknames ("FT"), slang ("bad guys"),
  several sentences, and 20 questions that must be refused. Its names are
  in no other set.

A prediction is **right** when it gives the same answer as the gold query
on the real world and on 24 reshuffled copies of it (so two queries that
mean the same thing both count). **Refused** means "ask another question"
for an answerable question: safe but annoying. **Misread** (a valid query
with another meaning) and **false_ok** (a query for an unanswerable
question) are the dangerous outcomes; the confirmation step exists for
them.

Scripts: `scripts/artist_bench.py` (any Ollama or OpenAI-compatible
server), `scripts/train_artist.py` (LoRA fine-tune), `scripts/export_artist.sh`
(GGUF export, quantise, CPU benchmark with llama-server).

## Results (2026-09-26)

Off-the-shelf models through Ollama, full prompt with examples, schema-
constrained, GPU (RTX 2080 Ti):

| Model | Size | test right | natural right | dangerous (test / natural) |
|---|---|---|---|---|
| gemma3 270m | 0.27B | 13% | 17% | 69% / 84% |
| SmolLM2 360m | 0.36B | 10% | 25% | 54% / 60% |
| qwen2.5 0.5b | 0.5B | 28% | 31% | 67% / 51% |
| qwen3 0.6b | 0.6B | 56% | 52% | 40% / 42% |
| llama3.2 1b | 1.2B | 24% | 25% | 72% / 72% |
| gemma3 1b | 1B | 34% | 40% | 60% / 54% |
| qwen2.5 1.5b | 1.5B | 47% | 52% | 53% / 46% |
| qwen3 1.7b | 1.7B | 61% | 66% | 36% / 30% |
| SmolLM2 1.7b | 1.7B | 37% | 35% | 59% / 55% |
| granite3.3 2b | 2B | 63% | 68% | 35% / 30% |
| llama3.2 3b | 3.2B | 70% | 67% | 30% / 32% |
| qwen2.5 3b | 3B | 73% | 66% | 27% / 32% |
| qwen3 4b | 4B | 81% | 81% | 18% / 19% |
| gemma3 4b | 4B | 81% | 76% | 19% / 24% |

General small models are not good enough: even at 4B, about one reading in
five is wrong.

Fine-tuned (LoRA rank 64, 30,000 generated examples, 2 epochs, compact
prompt, one RTX 2080 Ti, about 50 to 70 minutes per run):

| Model | Run | Decoding | test right | natural right | misread (test / natural) |
|---|---|---|---|---|---|
| Qwen2.5 0.5B | 1: 72 names | plain, GPU | 63% | 71% | 4.0% / 8.7% |
| Qwen2.5 0.5B | 1 | schema, CPU 8-bit | 88% | 84% | 11% / 17% |
| SmolLM2 360M | 1 | plain, GPU | 88% | 86% | 1.3% / 6.8% |
| Qwen2.5 0.5B | 2: 3,288 names | plain, GPU | 92% | 86% | 4.0% / 8.7% |
| Qwen2.5 0.5B | 2 | schema, CPU 8-bit | 91% | 85% | 9.3% / 15% |
| Qwen2.5 0.5B | 2 | plain, CPU 8-bit | 89% | 87% | 4.3% / 7.8% |
| **SmolLM2 360M** | **3: + new question families** | **plain, CPU 8-bit** | **91%** | **95%** | **6.7% / 3.9%** |
| SmolLM2 360M | 3 | plain, CPU 4-bit | 90% | 93% | 6.7% / 3.9% |

What the runs taught:

- **Names.** With 72 training names, models learned the names instead of
  copying them ("Rosa" for "Rowan"). 3,288 real and invented names fixed
  it (Qwen 63% to 92% on the test set).
- **Schema or not.** Forcing the output schema turns the fine-tuned
  model's uncertain answers into confident wrong ones: misreads doubled.
  The packaged model therefore uses plain decoding; the engine's
  validation turns bad output into "ask another question". General models
  (Ollama, cloud) keep the schema, which helps them.
- **Coverage.** Families the hand-written set exposed (neighbours, slang,
  "still alive", comparisons, neither/nor, greetings) were added as new
  training templates in run 3. The questions themselves were not copied,
  but the hand-written set is less independent from run 3 on; the
  generated test set remains fully independent.
- **Remaining errors** (run 3): "One of X and Y is the demon" read as
  *and*; "my right" sometimes read as left; "zero" read as "at least 0".
  Each is a template to add in a next round. The confirmation step shows
  the wrong reading to the player before anything is spent.

**Chosen packaged model:** SmolLM2 360M run 3. The 4-bit file is 271 MB
(phones), the 8-bit file 386 MB (computers). On a 4-core laptop-class CPU
it reads a question in 0.7 to 2.3 seconds (longer for 15-player tables with
the long character lists).

## Running it

The server asks at first start (`botc-automod --setup` to change). The
packaged model downloads llama.cpp (pinned `b11193`) and the model file
once, then runs on the CPU. On Android the app bundles llama.cpp's Android
build, so the packaged model runs on the phone. The model file needs a
public home for downloads (a Hugging Face repository is planned).
