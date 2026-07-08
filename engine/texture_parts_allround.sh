#!/usr/bin/env bash
# 既存パーツ(cloud_model.glb)に対して「全周テクスチャ」を付け直す。
# 各パーツ: デシメート → 横/後ろビューをCodex生成 → 全周投影(頂点カラー) → model.glb。
# 形状の再生成(Colab)は不要。有料画像APIは使わずCodexサブスクを使う。
#
# 使い方: texture_parts_allround.sh <parts_dir> [--faces 120000]

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"
BLENDER="${BLENDER_PATH:-/Applications/Blender.app/Contents/MacOS/Blender}"

PARTS_DIR="${1:-}"; shift || true
FACES="120000"
while [[ $# -gt 0 ]]; do case "$1" in --faces) FACES="$2"; shift 2;; *) shift 1;; esac; done
[[ -z "$PARTS_DIR" ]] && { echo "usage: texture_parts_allround.sh <parts_dir> [--faces N]" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONDA_SH"; conda activate "$ENV_NAME"

for pdir in "$PARTS_DIR"/*/; do
  name="$(basename "$pdir")"
  cloud="$pdir/cloud_model.glb"
  front="$pdir/front.png"
  [[ -f "$cloud" && -f "$front" ]] || { echo "skip $name (素材なし)"; continue; }
  if [[ -f "$pdir/model_allround.glb" ]]; then echo "skip $name (既存)"; cp "$pdir/model_allround.glb" "$pdir/model.glb"; continue; fi
  echo "=== $name ==="
  # 1) デシメート(色を載せるので少し高めの面数)
  "$BLENDER" --background --python "$SCRIPT_DIR/decimate.py" -- --mesh "$cloud" --out "$pdir/dec.glb" --faces "$FACES" >/dev/null 2>&1 \
    || { echo "  decimate失敗→cloud使用"; cp "$cloud" "$pdir/dec.glb"; }
  # 2) 横/後ろ/左ビューを生成(このパーツ単体の説明で)
  bash "$SCRIPT_DIR/gen_views.sh" "$front" "$pdir" "$name パーツ(建物の一部)" right back left >/dev/null 2>&1 || echo "  view生成一部失敗"
  # 3) 全周投影
  MV=(--view front="$front")
  for v in right back left; do [[ -f "$pdir/$v.png" ]] && MV+=(--view "$v=$pdir/$v.png"); done
  python "$SCRIPT_DIR/project_multiview.py" --mesh "$pdir/dec.glb" --out "$pdir/model.glb" --front-axis +z "${MV[@]}" \
    && cp "$pdir/model.glb" "$pdir/model_allround.glb" \
    || { echo "  投影失敗→front UVにフォールバック"; "$BLENDER" --background --python "$SCRIPT_DIR/bake_part.py" -- --mesh "$pdir/dec.glb" --image "$front" --out "$pdir/model.glb" --faces 0 >/dev/null 2>&1; }
  echo "  $name OK"
done
echo "全周テクスチャ完了"
