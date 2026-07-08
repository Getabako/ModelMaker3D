#!/usr/bin/env bash
# 正面画像を参照に、不足している方向のビュー(右横/後ろ/左横/上)を Codex の画像生成で作る。
# テクスチャ全周投影(multiview)用。有料画像APIは使わず Codexサブスクの image_gen を使う。
#
# 使い方:
#   gen_views.sh <正面画像> <出力DIR> "<対象の説明>" [right back left top ...]
#   省略時の生成ビュー: right back left
#
# 出力: <出力DIR>/right.png, back.png, left.png など。front は元画像をコピーして front.png に。

set -euo pipefail

FRONT="${1:-}"; OUTDIR="${2:-}"; SUBJECT="${3:-対象}"
shift 3 2>/dev/null || true
VIEWS=("$@")
[[ ${#VIEWS[@]} -eq 0 ]] && VIEWS=(right back left)

[[ -z "$FRONT" || -z "$OUTDIR" ]] && { echo "usage: gen_views.sh <front> <outdir> <subject> [views...]" >&2; exit 2; }
[[ -f "$FRONT" ]] || { echo "ERROR: 正面画像が見つかりません: $FRONT" >&2; exit 1; }
command -v codex >/dev/null 2>&1 || { echo "ERROR: codex CLI が必要です" >&2; exit 1; }
mkdir -p "$OUTDIR"
cp "$FRONT" "$OUTDIR/front.png" 2>/dev/null || true

# ビュー名 → 日本語の見え方
view_desc() {
  case "$1" in
    right) echo "右側面（真横・右から見た図）" ;;
    left)  echo "左側面（真横・左から見た図）" ;;
    back)  echo "背面（真後ろから見た図）" ;;
    top)   echo "真上から見た図（俯瞰）" ;;
    *)     echo "$1 から見た図" ;;
  esac
}

PRE="これは自動化された画像生成ジョブです。中央ナレッジベース確認・タスク報告などのセッション開始儀式は一切行わないでください。会話や前置きも不要。下記の画像を1枚だけ生成して保存し、保存パスのみ報告してください。"

for v in "${VIEWS[@]}"; do
  out="$OUTDIR/$v.png"
  desc="$(view_desc "$v")"
  echo "[gen_views] 生成: $v -> $out"
  codex exec -m gpt-5.5 -i "$FRONT" --sandbox workspace-write --dangerously-bypass-approvals-and-sandbox \
"${PRE}

参照画像は「${SUBJECT}」の正面図です。同じ対象・同じデザイン・同じ配色・同じ縮尺を厳密に保ったまま、【${desc}】を新規に描いてください。
- パース(遠近)をつけず、正面図と同じ平行投影(立面図)で描く。
- 背景は完全な単色グレー(#808080)。影・地面・人・文字は描かない。
- 対象1つだけ、全体が画面に収まるように。正面図と高さ・各階の位置を揃える。
- 1024x1024以上で「${out}」に保存。完了したらパスのみ報告。" \
    >/dev/null 2>&1 || echo "[gen_views] WARN: ${v} の生成に失敗" >&2
  if [[ -f "$out" ]]; then echo "[gen_views] OK: $out"; else echo "[gen_views] 未生成: $out" >&2; fi
done

echo "[gen_views] 完了"
