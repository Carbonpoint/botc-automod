#!/bin/bash
# Convert a fine-tuned run to GGUF, quantise it, and benchmark it on the CPU
# with llama-server (the same runtime the packaged model uses).
#
# Usage (on the training machine): scripts/export_artist.sh RUN_DIR [THREADS]
# Needs: ~/botc-train (uv env with gguf/transformers), llama.cpp-src and llama-bin there.
set -euo pipefail
RUN=$(realpath "$1"); THREADS=${2:-4}
TRAIN=$HOME/botc-train
BIN=$(dirname "$(find "$TRAIN/llama-bin" -name llama-quantize | head -1)")
export PATH=$HOME/.local/bin:$PATH LD_LIBRARY_PATH=$BIN
cd "$TRAIN"
uv run python llama.cpp-src/convert_hf_to_gguf.py "$RUN/merged" --outtype f16 --outfile "$RUN/model-f16.gguf" >/dev/null
for q in Q8_0 Q4_K_M; do
  "$BIN/llama-quantize" "$RUN/model-f16.gguf" "$RUN/model-$q.gguf" $q >/dev/null 2>&1
done
ls -la "$RUN"/*.gguf
cd "$HOME/botc-automod"
for q in f16 Q8_0 Q4_K_M; do
  port=$((8900 + RANDOM % 90))
  taskset -c 0-$((THREADS - 1)) "$BIN/llama-server" -m "$RUN/model-$q.gguf" --port $port -t "$THREADS" -c 2048 -np 1 \
      --no-webui >/tmp/llama-$port.log 2>&1 &
  pid=$!
  until curl -s "http://127.0.0.1:$port/health" | grep -q ok; do sleep 1; done
  uv run python scripts/artist_bench.py openai "http://127.0.0.1:$port/v1" "$(basename "$RUN")-$q" --compact \
      --n 300 --workers 1 --out "$RUN/cpu-$q.json" | sed "s/^/  /"
  kill $pid
done
echo EXPORT_DONE
