#!/usr/bin/env bash
# 人型/動物キャラ専用パイプライン(高品質既定)。正面[+横+後ろ]画像 → 形状 → 立て・溶接・スムーズ
# → 不足ビュー生成 → 本物UVテクスチャ(背景インペイント+手足補正) → Mixamo用FBX まで一括。
#
# これまでの学びを毎回自動適用する:
#  - TripoSRの横倒しを立てる(uv_bakeは up=+Y/front=+Z 前提) [[stand_smooth.py]]
#  - 頂点溶接 + スムーズ化 + スムーズシェードで表面を滑らかに
#  - top(頭頂)ビューをCodex生成して未塗り低減
#  - 背景インペイント(uv_bake既定) + 手足補正(--limb-fix)で腕の上下面のズレ/未塗り解消
#  - 正面軸 +z(顔/つま先が正面に出る)
#
# 使い方:
#   make3d_character.sh --front F.png [--side S.png] [--back B.png] --out DIR "<キャラ説明>" \
#       [--tris 15000] [--smooth 16] [--no-mixamo]
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"
BLENDER="${BLENDER_PATH:-/Applications/Blender.app/Contents/MacOS/Blender}"

FRONT=""; SIDE=""; BACK=""; OUT=""; SUBJECT="キャラクター"; TRIS="15000"; SMOOTH="16"; MIXAMO="1"; FACE="auto"; RES="256"
while [[ $# -gt 0 ]]; do case "$1" in
  --front) FRONT="$2"; shift 2;;
  --side)  SIDE="$2"; shift 2;;
  --back)  BACK="$2"; shift 2;;
  --out)   OUT="$2"; shift 2;;
  --tris)  TRIS="$2"; shift 2;;
  --smooth) SMOOTH="$2"; shift 2;;
  --face)  FACE="$2"; shift 2;;
  --res)   RES="$2"; shift 2;;
  --no-mixamo) MIXAMO="0"; shift 1;;
  *) SUBJECT="$1"; shift 1;;
esac; done
[[ -z "$FRONT" || -z "$OUT" ]] && { echo "usage: make3d_character.sh --front F.png [--side S][--back B] --out DIR <subject>" >&2; exit 2; }
mkdir -p "$OUT"
# shellcheck disable=SC1090
source "$CONDA_SH"; conda activate "$ENV_NAME"

cp "$FRONT" "$OUT/front.png"
[[ -n "$BACK" ]] && cp "$BACK" "$OUT/back.png"
# 横: side をそのまま right、ミラーを left に(対称キャラ想定)
if [[ -n "$SIDE" ]]; then
  python - "$SIDE" "$OUT" <<'PY'
import sys; from PIL import Image; import os
s=Image.open(sys.argv[1]).convert("RGB"); o=sys.argv[2]
s.save(os.path.join(o,"right.png")); s.transpose(Image.FLIP_LEFT_RIGHT).save(os.path.join(o,"left.png"))
PY
fi

echo "=== [1/5] 形状生成(TripoSR, 正面) ==="
bash "$SCRIPT_DIR/run_triposr.sh" --image "$OUT/front.png" --out "$OUT/_geo" --mc-resolution "$RES"
[[ -f "$OUT/_geo/mesh.obj" ]] || { echo "ERROR: 形状生成失敗" >&2; exit 1; }

echo "=== [2/5] 立て・溶接・スムーズ ==="
"$BLENDER" --background --python "$SCRIPT_DIR/stand_smooth.py" -- --mesh "$OUT/_geo/mesh.obj" --out "$OUT/chibi_smooth.glb" --smooth "$SMOOTH" --face "$FACE" 2>&1 | grep -iE "stand_smooth|ERROR"

echo "=== [3/5] 不足ビュー生成(top, 必要なら back/left/right) ==="
need=()
for v in top; do [[ -f "$OUT/$v.png" ]] || need+=("$v"); done
[[ -z "$BACK" && ! -f "$OUT/back.png" ]] && need+=(back)
[[ -z "$SIDE" && ! -f "$OUT/right.png" ]] && need+=(right left)
[[ ${#need[@]} -gt 0 ]] && bash "$SCRIPT_DIR/gen_views.sh" "$OUT/front.png" "$OUT" "$SUBJECT" "${need[@]}" >/dev/null 2>&1 || true

echo "=== [4/5] 本物UVテクスチャ(Smart UV→マルチビュー・ブレンド+オクルージョン+背景インペイント) ==="
# Meshy的: UV展開→全ビューを法線重みでブレンド→隠れ面は深度判定で除外→未塗りはインペイント。
if "$BLENDER" --background --python "$SCRIPT_DIR/smart_uv.py" -- --mesh "$OUT/chibi_smooth.glb" --out "$OUT/chibi_uv.glb" --angle 70 --margin 0.001 2>&1 | grep -q "smart_uv] OK"; then
  python "$SCRIPT_DIR/uv_bake_multiview.py" --mesh "$OUT/chibi_uv.glb" --views "$OUT" \
    --out "$OUT/model_uv.glb" --atlas "$OUT/atlas.png" --front-axis +z --size 2048 --power 3.0
else
  echo "  smart_uv失敗→キューブ投影(手足補正)にフォールバック"
  python "$SCRIPT_DIR/uv_bake_part.py" --mesh "$OUT/chibi_smooth.glb" --views "$OUT" \
    --out "$OUT/model_uv.glb" --atlas "$OUT/atlas.png" --front-axis +z --cell 1024 --limb-fix
fi

echo "=== [4.5/5] 正面照合ゲート(前後逆の自動検出→自動反転リトライ) ==="
run_bake() {  # $1=faceモード
  "$BLENDER" --background --python "$SCRIPT_DIR/stand_smooth.py" -- --mesh "$OUT/_geo/mesh.obj" --out "$OUT/chibi_smooth.glb" --smooth "$SMOOTH" --face "$1" 2>&1 | grep -iE "stand_smooth|ERROR"
  if "$BLENDER" --background --python "$SCRIPT_DIR/smart_uv.py" -- --mesh "$OUT/chibi_smooth.glb" --out "$OUT/chibi_uv.glb" --angle 70 --margin 0.001 2>&1 | grep -q "smart_uv] OK"; then
    python "$SCRIPT_DIR/uv_bake_multiview.py" --mesh "$OUT/chibi_uv.glb" --views "$OUT" \
      --out "$OUT/model_uv.glb" --atlas "$OUT/atlas.png" --front-axis +z --size 2048 --power 3.0
  else
    python "$SCRIPT_DIR/uv_bake_part.py" --mesh "$OUT/chibi_smooth.glb" --views "$OUT" \
      --out "$OUT/model_uv.glb" --atlas "$OUT/atlas.png" --front-axis +z --cell 1024 --limb-fix
  fi
}
verify_front() {
  rm -rf "$OUT/_verify"; mkdir -p "$OUT/_verify"
  "$BLENDER" --background --python "$SCRIPT_DIR/snap_views.py" -- --mesh "$OUT/model_uv.glb" --out "$OUT/_verify" --prefix snap >/dev/null 2>&1
  python "$SCRIPT_DIR/verify_front.py" --render "$OUT/_verify/snap_front.png" --front "$OUT/front.png" --back "$OUT/back.png"
}
if [[ -f "$OUT/back.png" ]]; then
  if ! verify_front; then
    echo "  前後逆を検出 → 反転して再ベイク"
    run_bake flip
    verify_front || echo "  WARNING: 反転後も照合NG。目視確認してください" >&2
  fi
else
  echo "  back.png が無いため照合スキップ"
fi

echo "=== [5/5] Mixamo用FBX ==="
if [[ "$MIXAMO" == "1" ]]; then
  "$BLENDER" --background --python "$SCRIPT_DIR/prep_mixamo.py" -- --mesh "$OUT/model_uv.glb" --out "$OUT/for_mixamo.fbx" --scale 1.0 2>&1 | grep -iE "prep_mixamo|ERROR"
fi

echo "=== Procreate用USDZ ==="
"$BLENDER" --background --python "$SCRIPT_DIR/export_usdz.py" -- --mesh "$OUT/model_uv.glb" --out "$OUT/model.usdz" 2>&1 | grep -iE "export_usdz|ERROR" || echo "[character] USDZ 書き出し失敗(GLBはあります)" >&2

echo ""
echo "=== 完成 ==="
echo "  確認用: $OUT/model_uv.glb"
[[ "$MIXAMO" == "1" ]] && echo "  Mixamo: $OUT/for_mixamo.fbx (リグは rig_mixamo.sh / Mixyサイトで)"
[[ -f "$OUT/model.usdz" ]] && echo "  Procreate: $OUT/model.usdz"
ls -la "$OUT/model_uv.glb" 2>/dev/null | awk '{print $5,$9}'
