#!/usr/bin/env bash
# パーツ分割パイプライン: 参照画像 → 部品分解 → 部品ごとに形状(cloud)+本物UVテクスチャ → 統合。
# 「最高品質」狙い。時間はかかる(部品数 × 形状生成)。
#
# 使い方:
#   make3d_parts.sh <参照画像> --out <DIR> "<対象説明>" [--only name1,name2] [--endpoint URL] [--height 2.0] [--aspect 1.0] [--skip-decompose]
#
# 事前に Colab(ModelMaker3D_Cloud.ipynb)を起動し ~/.modelmaker3d_cloud に公開URLを保存しておく。

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"
BLENDER="${BLENDER_PATH:-/Applications/Blender.app/Contents/MacOS/Blender}"

FRONT="${1:-}"; shift || true
OUT=""; SUBJECT=""; ONLY=""; ENDPOINT=""; HEIGHT="2.0"; ASPECT="1.0"; SKIP_DECOMP="0"
TRIS="12000"; CLEAN="0"; SQUARE="0.9"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --height) HEIGHT="$2"; shift 2 ;;
    --aspect) ASPECT="$2"; shift 2 ;;
    --tris) TRIS="$2"; shift 2 ;;           # ゲーム向けポリ数(各パーツ)
    --square-depth) SQUARE="$2"; shift 2 ;; # 奥行=幅×係数(浅すぎ対策)。0で無効
    --clean) CLEAN="1"; shift 1 ;;          # Codexでアトラス清書(AI仕上げ)
    --skip-decompose) SKIP_DECOMP="1"; shift 1 ;;
    *) SUBJECT="$1"; shift 1 ;;
  esac
done
[[ -z "$FRONT" || -z "$OUT" ]] && { echo "usage: make3d_parts.sh <image> --out DIR <subject> [--only a,b] ..." >&2; exit 2; }
mkdir -p "$OUT"
# shellcheck disable=SC1090
source "$CONDA_SH"; conda activate "$ENV_NAME"

[[ -z "$ENDPOINT" ]] && ENDPOINT="$(cat "$HOME/.modelmaker3d_cloud" 2>/dev/null | tr -d '[:space:]')"
[[ -z "$ENDPOINT" ]] && { echo "ERROR: Colab公開URLが必要(~/.modelmaker3d_cloud)" >&2; exit 2; }

# 1) 分解
if [[ "$SKIP_DECOMP" != "1" || ! -f "$OUT/parts.json" ]]; then
  echo "=== [1/4] 部品分解 ==="
  bash "$SCRIPT_DIR/decompose.sh" "$FRONT" "$OUT" "$SUBJECT"
fi
[[ -f "$OUT/parts.json" ]] || { echo "ERROR: parts.json なし" >&2; exit 1; }

# 2) 切り出し
echo "=== [2/4] パーツ切り出し ==="
python "$SCRIPT_DIR/crop_parts.py" "$OUT/parts.json" "$FRONT" "$OUT/parts"

# 対象パーツ一覧
NAMES=$(python - "$OUT/parts.json" "$ONLY" <<'PY'
import json,sys
spec=json.load(open(sys.argv[1])); only=set([x for x in sys.argv[2].split(",") if x])
for p in spec["parts"]:
    if not only or p["name"] in only:
        print(p["name"])
PY
)

# 3) パーツごとに 形状(cloud) を生成
echo "=== [3/4] パーツ毎 形状生成(cloud) ==="
for name in $NAMES; do
  pdir="$OUT/parts/$name"
  img="$pdir/front.png"
  [[ -f "$img" ]] || { echo "  - $name: front.png なし、skip"; continue; }
  if [[ -f "$pdir/cloud_model.glb" ]]; then echo "  - $name: 既存 cloud_model.glb をスキップ"; continue; fi
  echo "  - $name: 形状生成(cloud)..."
  python "$SCRIPT_DIR/cloud_generate.py" --endpoint "$ENDPOINT" --image "$img" --out "$pdir/cloud_model.glb" --steps 30 \
    || echo "    形状生成失敗: $name"
done

# 3b) 低ポリ化 + キューブ投影UV + 投影ベイク(本物UVテクスチャ) [+Codex清書]
echo "=== [3b/4] 低ポリ化 + UVテクスチャ ==="
CLEAN_FLAG=""; [[ "$CLEAN" == "1" ]] && CLEAN_FLAG="--clean"
bash "$SCRIPT_DIR/uv_texture_parts.sh" "$OUT/parts" --tris "$TRIS" --subject "$SUBJECT" $CLEAN_FLAG

# 4) 統合(パーツは別オブジェクトのまま=手動編集向け / 奥行きは幅×SQUARE で正方形寄せ)
echo "=== [4/4] 統合 ==="
SQ_FLAG=""; [[ "$SQUARE" != "0" ]] && SQ_FLAG="--square-depth $SQUARE"
"$BLENDER" --background --python "$SCRIPT_DIR/assemble.py" -- \
  --parts-json "$OUT/parts.json" --parts-dir "$OUT/parts" \
  --model-name model_uv.glb --no-join 1 --center-x 1 $SQ_FLAG \
  --out "$OUT/model.glb" --fbx "$OUT/model.fbx" --height "$HEIGHT" --aspect "$ASPECT" 2>&1 | grep -iE "placed|GLB|FBX|ERROR|skip" | tail -30

echo ""
echo "=== 完成: $OUT/model.glb (各パーツ parts/<name>/model_uv.glb / atlas.png) ==="
ls -la "$OUT/model.glb" "$OUT/model.fbx" 2>/dev/null