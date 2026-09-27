#!/usr/bin/env bash
# Render video (8 parallel workers) + score, then mux into the final mp4.
# Usage: ./build.sh WORKDIR OUTPUT.mp4
set -euo pipefail
cd "$(dirname "$0")"
WORK="$1"; OUT="$2"; JOBS="${JOBS:-8}"
FFMPEG="${FFMPEG:-$(python3 -c "from render import FFMPEG; print(FFMPEG)")}"
mkdir -p "$WORK"
rm -f "$WORK"/seg_*.mp4 "$WORK"/log_*.txt
start=$(date +%s)
python3 audio.py "$WORK/score.wav" > "$WORK/log_audio.txt" 2>&1 &
pids=()
for ((i = 0; i < JOBS; i++)); do
  python3 render.py worker "$i" "$JOBS" "$WORK" > "$WORK/log_$i.txt" 2>&1 &
  pids+=($!)
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
wait
[[ $fail == 0 ]] || { echo "a render worker failed"; tail -n 5 "$WORK"/log_*.txt; exit 1; }
cat "$WORK/log_audio.txt"
: > "$WORK/list.txt"
for ((i = 0; i < JOBS; i++)); do printf "file '%s'\n" "$WORK/$(printf 'seg_%02d.mp4' "$i")" >> "$WORK/list.txt"; done
"$FFMPEG" -y -loglevel error -f concat -safe 0 -i "$WORK/list.txt" -i "$WORK/score.wav" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -movflags +faststart -shortest "$OUT"
echo "done in $(( $(date +%s) - start ))s -> $OUT"
