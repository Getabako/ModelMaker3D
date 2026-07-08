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
#       [--geo auto|cloud|local] [--endpoint URL] [--tris 15000] [--smooth 16] [--no-mixamo]
#
# 形状エンジン(--geo):
#   auto(既定)  = Colab(Hunyuan3D-2)が生きていれば cloud、死んでいれば警告して local へ
#   cloud       = Colab必須(未接続ならエラー)。L4+ENABLE_PAINT なら本物UVテクスチャ付きで返り、
#                 ローカルベイクを省略して品質最優先の成果物になる
#   local       = 従来のTripoSR(品質は落ちる。Colabが使えない時のみ)
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"
BLENDER="${BLENDER_PATH:-/Applications/Blender.app/Contents/MacOS/Blender}"

FRONT=""; SIDE=""; BACK=""; OUT=""; SUBJECT="キャラクター"; TRIS="15000"; SMOOTH="16"; MIXAMO="1"; FACE="auto"; RES="256"
GEO="auto"; ENDPOINT=""
while [[ $# -gt 0 ]]; do case "$1" in
  --front) FRONT="$2"; shift 2;;
  --side)  SIDE="$2"; shift 2;;
  --back)  BACK="$2"; shift 2;;
  --out)   OUT="$2"; shift 2;;
  --tris)  TRIS="$2"; shift 2;;
  --smooth) SMOOTH="$2"; shift 2;;
  --face)  FACE="$2"; shift 2;;
  --res)   RES="$2"; shift 2;;
  --geo)   GEO="$2"; shift 2;;        # auto(既定: cloud優先)|cloud(必須)|local(TripoSR)
  --endpoint) ENDPOINT="$2"; shift 2;;
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

# --- 形状エンジン解決: 品質既定は cloud(Hunyuan3D-2)。未接続なら local にフォールバック ---
CLOUD_URL=""
if [[ "$GEO" != "local" ]]; then
  CLOUD_URL="${ENDPOINT:-${MODELMAKER_CLOUD_URL:-}}"
  [[ -z "$CLOUD_URL" && -f "$HOME/.modelmaker3d_cloud" ]] && CLOUD_URL="$(tr -d '[:space:]' < "$HOME/.modelmaker3d_cloud")"
  if [[ -n "$CLOUD_URL" ]] && curl -s -m 8 -o /dev/null "$CLOUD_URL/health"; then
    echo "[character] 形状エンジン: cloud(Hunyuan3D-2) $CLOUD_URL"
  else
    if [[ "$GEO" == "cloud" ]]; then
      echo "ERROR: Colabエンドポイントに接続できません。colab/ModelMaker3D_Cloud.ipynb を実行し、URLを ~/.modelmaker3d_cloud に保存してください" >&2
      exit 2
    fi
    echo "WARNING: Colab未接続 → ローカルTripoSRにフォールバック(品質は cloud より落ちる。高品質にするなら Colab を起動)" >&2
    CLOUD_URL=""
  fi
fi

TEXTURED="False"
mkdir -p "$OUT/_geo"
if [[ -n "$CLOUD_URL" ]]; then
  echo "=== [1/5] 形状生成(Hunyuan3D-2 cloud, 正面) ==="
  # A100前提で最高設定(octree 512)。品質を控えない。
  python "$SCRIPT_DIR/cloud_generate.py" --endpoint "$CLOUD_URL" --image "$OUT/front.png" \
    --out "$OUT/_geo/cloud_model.glb" --steps 50 --octree 512
  [[ -f "$OUT/_geo/cloud_model.glb" ]] || { echo "ERROR: cloud形状生成失敗" >&2; exit 1; }
  TEXTURED="$(python -c "import json;print(json.load(open('$OUT/_geo/cloud_model_meta.json')).get('textured',False))" 2>/dev/null || echo False)"
  GEO_MESH="$OUT/_geo/cloud_model.glb"
else
  echo "=== [1/5] 形状生成(TripoSR, 正面) ==="
  bash "$SCRIPT_DIR/run_triposr.sh" --image "$OUT/front.png" --out "$OUT/_geo" --mc-resolution "$RES"
  [[ -f "$OUT/_geo/mesh.obj" ]] || { echo "ERROR: 形状生成失敗" >&2; exit 1; }
  GEO_MESH="$OUT/_geo/mesh.obj"
fi

# --- cloudのpaint(本物UVテクスチャ)付きで返ってきた場合: ローカルベイクを丸ごとスキップ ---
if [[ "$TEXTURED" == "True" ]]; then
  echo "=== [2-4/5] Hunyuan3D paintテクスチャ採用(ローカルベイク省略) ==="
  cp "$OUT/_geo/cloud_model.glb" "$OUT/model_uv.glb"
  # 正面照合(前後逆なら180°回して再照合)。back.png が無ければ生成して照合する
  if [[ ! -f "$OUT/back.png" ]]; then
    bash "$SCRIPT_DIR/gen_views.sh" "$OUT/front.png" "$OUT" "$SUBJECT" back >/dev/null 2>&1 || true
  fi
  verify_cloud_front() {
    rm -rf "$OUT/_verify"; mkdir -p "$OUT/_verify"
    "$BLENDER" --background --python "$SCRIPT_DIR/snap_views.py" -- --mesh "$OUT/model_uv.glb" --out "$OUT/_verify" --prefix snap >/dev/null 2>&1
    python "$SCRIPT_DIR/verify_front.py" --render "$OUT/_verify/snap_front.png" --front "$OUT/front.png" --back "$OUT/back.png"
  }
  if [[ -f "$OUT/back.png" ]]; then
    if ! verify_cloud_front; then
      echo "  前後逆を検出 → 180°回転"
      "$BLENDER" --background --python "$SCRIPT_DIR/rotate_yaw.py" -- --mesh "$OUT/_geo/cloud_model.glb" --out "$OUT/model_uv.glb" --deg 180 2>&1 | grep -iE "rotate_yaw|ERROR"
      verify_cloud_front || echo "  WARNING: 回転後も照合NG。目視確認してください" >&2
    fi
  else
    echo "  back.png 無し(生成も失敗)のため照合スキップ"
  fi

  echo "=== [5/5] Mixamo用FBX ==="
  if [[ "$MIXAMO" == "1" ]]; then
    "$BLENDER" --background --python "$SCRIPT_DIR/prep_mixamo.py" -- --mesh "$OUT/model_uv.glb" --out "$OUT/for_mixamo.fbx" --scale 1.0 2>&1 | grep -iE "prep_mixamo|ERROR"
  fi
  echo "=== Procreate用USDZ ==="
  "$BLENDER" --background --python "$SCRIPT_DIR/export_usdz.py" -- --mesh "$OUT/model_uv.glb" --out "$OUT/model.usdz" 2>&1 | grep -iE "export_usdz|ERROR" || echo "[character] USDZ 書き出し失敗(GLBはあります)" >&2

  echo ""
  echo "=== 完成(cloud/paint) ==="
  echo "  確認用: $OUT/model_uv.glb"
  [[ "$MIXAMO" == "1" ]] && echo "  Mixamo: $OUT/for_mixamo.fbx"
  [[ -f "$OUT/model.usdz" ]] && echo "  Procreate: $OUT/model.usdz"
  ls -la "$OUT/model_uv.glb" 2>/dev/null | awk '{print $5,$9}'
  exit 0
fi

echo "=== [2/5] 立て・溶接・スムーズ ==="
"$BLENDER" --background --python "$SCRIPT_DIR/stand_smooth.py" -- --mesh "$GEO_MESH" --out "$OUT/chibi_smooth.glb" --smooth "$SMOOTH" --face "$FACE" 2>&1 | grep -iE "stand_smooth|ERROR"

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
  "$BLENDER" --background --python "$SCRIPT_DIR/stand_smooth.py" -- --mesh "$GEO_MESH" --out "$OUT/chibi_smooth.glb" --smooth "$SMOOTH" --face "$1" 2>&1 | grep -iE "stand_smooth|ERROR"
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
