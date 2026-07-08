#!/usr/bin/env bash
# 人型/動物モデルを Mixamo でリギング+アニメするための準備。
# Mixamo はブラウザでの手動アップロードが必須(自動化不可)なので、
# ここでは「Mixamoに通りやすい形」にFBXを整形 → サイトを開く → 手順を表示する。
#
# 使い方:
#   rig_mixamo.sh <model.glb または .fbx> [--out DIR] [--scale 1.0]
#
# 整形内容: 1メッシュに統合・原点を足元中央・前向きを-Y(Mixamo想定)・適度なスケール・FBX(埋め込みテクスチャ)出力。

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLENDER="${BLENDER_PATH:-/Applications/Blender.app/Contents/MacOS/Blender}"
MODEL="${1:-}"; shift || true
OUTDIR=""; SCALE="1.0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUTDIR="$2"; shift 2 ;;
    --scale) SCALE="$2"; shift 2 ;;
    *) shift 1 ;;
  esac
done
[[ -z "$MODEL" ]] && { echo "usage: rig_mixamo.sh <model.glb|fbx> [--out DIR] [--scale 1.0]" >&2; exit 2; }
[[ -f "$MODEL" ]] || { echo "ERROR: モデルが見つかりません: $MODEL" >&2; exit 1; }
[[ -z "$OUTDIR" ]] && OUTDIR="$(dirname "$MODEL")"
mkdir -p "$OUTDIR"
FBX="$OUTDIR/for_mixamo.fbx"

"$BLENDER" --background --python "$SCRIPT_DIR/prep_mixamo.py" -- --mesh "$MODEL" --out "$FBX" --scale "$SCALE" 2>&1 | grep -iE "prep_mixamo|ERROR" | tail
[[ -f "$FBX" ]] || { echo "ERROR: FBX書き出し失敗" >&2; exit 1; }

# Mixamoを開く
command -v open >/dev/null 2>&1 && open "https://www.mixamo.com/#/?page=1&type=Character"

cat <<EOF

============================================================
  Mixamo リギング手順 (無料・要 Adobe アカウント)
------------------------------------------------------------
  1. 開いた Mixamo にログイン
  2. 右上「UPLOAD CHARACTER」→ 次のFBXをアップロード:
       $FBX
  3. 自動リグ画面で、あご/手首/肘/膝/股 のマーカーを体に合わせる → NEXT
  4. リグ完了後、左の Animations から好きなモーションを選ぶ
  5. DOWNLOAD → Format: FBX Binary, With Skin → 保存
  6. 受け取ったFBX(ボーン+アニメ入り)を Unity/Blender で使用
------------------------------------------------------------
  ※ Mixamo は人型に最適。動物/非標準体型は Blender Rigify を使う(別途案内)。
============================================================
EOF
