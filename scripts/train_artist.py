"""Fine-tune a small model to translate Artist questions into queries (LoRA).

Runs on a CUDA machine inside a training environment (torch, transformers,
peft, accelerate). The botc-automod source must be importable (PYTHONPATH).

  python scripts/train_artist.py --base Qwen/Qwen2.5-0.5B-Instruct --out runs/q05 --gpu 0

Writes the merged model to OUT/merged and a score report to OUT/eval.json.
"""
import argparse
import json
import os
import random
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--gpu", default="0")
ap.add_argument("--n-train", type=int, default=30000)
ap.add_argument("--epochs", type=float, default=2.0)
ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--rank", type=int, default=64)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--full", action="store_true", help="full fine-tune instead of LoRA")
a = ap.parse_args()
os.environ["CUDA_VISIBLE_DEVICES"] = a.gpu

import torch  # noqa: E402
from peft import LoraConfig, get_peft_model  # noqa: E402
from transformers import (AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq,  # noqa: E402
                          Trainer, TrainingArguments)

from botc_automod.artist import dataset  # noqa: E402
from botc_automod.artist.translate import SYSTEM_COMPACT, user_message  # noqa: E402

tok = AutoTokenizer.from_pretrained(a.base)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token


def target(gold: dict) -> str:
    return json.dumps({"query": gold}, separators=(",", ":"))


def prompt_ids(world, asker, question):
    msgs = [{"role": "system", "content": SYSTEM_COMPACT},
            {"role": "user", "content": user_message(world, asker, question)}]
    kw = {"enable_thinking": False} if "qwen3" in a.base.lower() else {}
    text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, **kw)
    return tok(text, add_special_tokens=False)["input_ids"]


END = tok.eos_token_id if tok.convert_ids_to_tokens(tok.eos_token_id) != "<|endoftext|>" else \
    tok.convert_tokens_to_ids("<|im_end|>")


def encode(ex):
    w = dataset.world_from_json(ex["world"])
    p = prompt_ids(w, ex["asker"], ex["question"])
    c = tok(target(ex["gold"]), add_special_tokens=False)["input_ids"] + [END]
    return {"input_ids": p + c, "attention_mask": [1] * (len(p) + len(c)), "labels": [-100] * len(p) + c}


print("generating data", flush=True)
train = [encode(e) for e in dataset.generate(a.n_train, "train", seed=7)]
print("examples", len(train), "max tokens", max(len(x["input_ids"]) for x in train), flush=True)

model = AutoModelForCausalLM.from_pretrained(a.base, torch_dtype=torch.float32)
if not a.full:
    model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05,
                                             target_modules="all-linear", task_type="CAUSAL_LM"))
    model.print_trainable_parameters()

args = TrainingArguments(output_dir=f"{a.out}/ckpt", per_device_train_batch_size=a.batch, gradient_accumulation_steps=1,
                         num_train_epochs=a.epochs, learning_rate=a.lr, lr_scheduler_type="cosine", warmup_ratio=0.03,
                         logging_steps=50, save_strategy="no", fp16=True, report_to=[], dataloader_num_workers=2,
                         group_by_length=True)
t0 = time.time()
Trainer(model=model, args=args, train_dataset=train,
        data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)).train()
print(f"trained in {time.time() - t0:.0f}s", flush=True)

if not a.full:
    model = model.merge_and_unload()
model = model.to(torch.float16)
model.save_pretrained(f"{a.out}/merged")
tok.save_pretrained(f"{a.out}/merged")

# Score with plain greedy decoding (no grammar): the hardest setting.
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from artist_bench import natural_items, score  # noqa: E402

from botc_automod.artist.translate import Translator  # noqa: E402


class HF(Translator):
    compact = True

    def complete(self, system, user, world):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        kw = {"enable_thinking": False} if "qwen3" in a.base.lower() else {}
        text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, **kw)
        ids = tok(text, add_special_tokens=False, return_tensors="pt")["input_ids"].to("cuda")
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=200, do_sample=False, pad_token_id=tok.pad_token_id)
        return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)


model = model.to("cuda").eval()
report = {"base": a.base, "n_train": a.n_train, "epochs": a.epochs, "rank": a.rank, "full": a.full}
for name, items in {"test": dataset.generate(300, "test", seed=99), "natural": natural_items(random.Random(3))}.items():
    r = score(HF(), items, workers=1)
    report[name] = r
    print(f"{a.base} {name}: right {r['right_pct']}%  refused {r['refused']}  misread {r['misread']}  "
          f"false_ok {r['false_ok']}  dangerous {r['dangerous_pct']}%", flush=True)
with open(f"{a.out}/eval.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=1)
print("TRAIN_DONE", flush=True)
