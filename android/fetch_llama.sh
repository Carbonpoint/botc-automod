#!/bin/bash
# Put llama.cpp's Android build (pinned) into jniLibs, so the app can run the packaged
# Artist model on the phone. Android only lets an app run programs from its native
# library folder, so llama-server is stored under a library name.
# Run once before building: ./fetch_llama.sh   (the files are not in git)
set -euo pipefail
TAG=b11193
DEST=app/src/main/jniLibs/arm64-v8a
cd "$(dirname "$0")"
[ -f "$DEST/libllama-server-exec.so" ] && { echo "already present"; exit 0; }
tmp=$(mktemp -d)
curl -sL "https://github.com/ggml-org/llama.cpp/releases/download/$TAG/llama-$TAG-bin-android-arm64.tar.gz" | tar xz -C "$tmp"
src="$tmp/llama-$TAG"
mkdir -p "$DEST"
cp "$src/llama-server" "$DEST/libllama-server-exec.so"
for f in libllama-server-impl.so libllama-common.so libmtmd.so libllama.so libggml.so libggml-base.so "$src"/libggml-cpu-*.so; do
  cp "$src/$(basename "$f")" "$DEST/"
done
# Strip debug symbols when the NDK is at hand (26 MB instead of about 230 MB).
STRIP=$(ls "${ANDROID_HOME:-$HOME/android-dev/sdk}"/ndk/*/toolchains/llvm/prebuilt/*/bin/llvm-strip 2>/dev/null | tail -1 || true)
[ -n "$STRIP" ] && for f in "$DEST"/*.so; do "$STRIP" "$f"; done
rm -rf "$tmp"
du -sh "$DEST"
