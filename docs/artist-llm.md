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

## Results so far (2026-09-26)

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

Fine-tuned (LoRA, 30,000 generated examples, 2 epochs, compact prompt):

| Model | Setting | test right | natural right | dangerous (test / natural) |
|---|---|---|---|---|
| Qwen2.5 0.5B, run 1 | plain decoding | 63% | 71% | 4.0% / 8.7% |
| Qwen2.5 0.5B, run 1 | llama.cpp, schema, CPU, 8-bit | 88% | 84% | 11% / 17% |
| SmolLM2 360M, run 1 | plain decoding | 88% | 86% | 1.3% / 6.8% |

Run 1 used only 72 training names, and the models learned the names
instead of copying them from the question ("Rosa" for "Rowan"). Runs 2 and
3 use 3,288 names (real and invented) and add question families the
hand-written set showed were missing (neighbours, slang, comparisons,
"still alive", neither/nor, greetings to refuse).

On a 4-core laptop-class CPU, the 8-bit SmolLM2 model (386 MB; 271 MB at
4-bit) reads a question in 0.5 to 1.1 seconds through llama-server.

## Running it

The server asks at first start (`botc-automod --setup` to change). The
packaged model downloads llama.cpp (pinned `b11193`) and the model file
once, then runs on the CPU. On Android the app bundles llama.cpp's Android
build, so the packaged model runs on the phone. The model file needs a
public home for downloads (a Hugging Face repository is planned).
