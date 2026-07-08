#!/usr/bin/env bash
# 各パーツを「低ポリ化 → キューブ投影UV → 各方向画像を投影ベイク(本物UVテクスチャ) →(任意)Codex清書」する。
# 頂点カラーではなく解像度がポリ数に依存しない2Dテクスチャを作るので、低ポリでも鮮明。
# 出力: parts/<name>/model_uv.glb, atlas.png (--clean時は atlas_clean.png を再適用)
#
# 使い方:
#   uv_texture_parts.sh <parts_dir> [--tris 12000] [--cell 1024] [--clean] [--force] [--subject "安土城"]
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"
BLENDER="${BLENDER_PATH:-/Applications/Blender.app/Contents/MacOS/Blender}"

PARTS_DIR="${1:-}"; shift || true
TRIS="12000"; CELL="1024"; CLEAN="0"; FORCE="0"; SUBJECT="建物"; CLEAN_ONLY="0"
while [[ $# -gt 0 ]]; do case "$1" in
  --tris) TRIS="$2"; shift 2;;
  --cell) CELL="$2"; shift 2;;
  --clean) CLEAN="1"; shift 1;;
  --clean-only) CLEAN="1"; CLEAN_ONLY="1"; shift 1;;
  --force) FORCE="1"; shift 1;;
  --subject) SUBJECT="$2"; shift 2;;
  *) shift 1;; esac; done
[[ -z "$PARTS_DIR" ]] && { echo "usage: uv_texture_parts.sh <parts_dir> [--tris N] [--cell N] [--clean] [--force] [--subject S]" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONDA_SH"; conda activate "$ENV_NAME"

PRE="これは自動化された画像生成ジョブです。セッション開始儀式や前置きは一切不要。指定画像を1枚生成・保存し、保存パスのみ報告。"

for pdir in "$PARTS_DIR"/*/; do
  name="$(basename "$pdir")"
  cloud="$pdir/cloud_model.glb"; front="$pdir/front.png"
  [[ -f "$cloud" && -f "$front" ]] || { echo "skip $name (素材なし)"; continue; }
  if [[ "$CLEAN_ONLY" == "0" && "$FORCE" == "0" && -f "$pdir/model_uv.glb" ]]; then echo "skip $name (既存 model_uv.glb)"; continue; fi
  echo "=== $name ==="

  # clean-only: 既存 atlas.png/dec_uv.glb を使い、Codex清書→再適用のみ
  if [[ "$CLEAN_ONLY" == "1" ]]; then
    [[ -f "$pdir/atlas.png" && -f "$pdir/dec_uv.glb" ]] || { echo "  skip(atlas/dec無し)"; continue; }
    if [[ -f "$pdir/atlas_clean.png" && "$FORCE" == "0" ]]; then
      echo "  既存 atlas_clean.png を再適用"
    else
      echo "  Codex清書..."
      codex exec -m gpt-5.5 -i "$pdir/atlas.png" --sandbox workspace-write --dangerously-bypass-approvals-and-sandbox \
"${PRE}

これは3Dモデルのテクスチャアトラス(3列×2行グリッド)。$SUBJECT の $name パーツを各方向から見た正射図が並ぶ(左上=正面,中上=右,右上=背面,左下=左,中下=上面,右下=下面)。次の条件で清書し同レイアウトで保存:
- グリッド分割位置・各セル内の絵の位置/スケール/構図を1ピクセルも動かさない(UV一致のため厳守)。
- 白い背景や余白は周囲の素材色で自然に塗りつぶす。背景に物体を増やさない。
- 素材感(石垣/漆喰/木部/瓦/金具)をくっきり鮮明に。配色は元のまま。
- 灰色一色のセル(情報なしの面)はそのパーツを真上/真下から見た妥当な見た目で描く(背景#8a8a8a)。
- 出力は入力と同じ3列×2行・同じ縦横比PNG。「$pdir/atlas_clean.png」に保存しパスのみ報告。" \
        >/dev/null 2>&1 || echo "  WARN: Codex清書失敗"
    fi
    if [[ -f "$pdir/atlas_clean.png" ]]; then
      python "$SCRIPT_DIR/uv_bake_part.py" --mesh "$pdir/dec_uv.glb" --views "$pdir" \
          --out "$pdir/model_uv.glb" --atlas "$pdir/atlas_used.png" --front-axis +z --cell "$CELL" \
          --atlas-in "$pdir/atlas_clean.png" >/dev/null 2>&1 \
        && echo "  $name 清書を再適用 OK" || echo "  WARN: 再適用失敗"
    fi
    continue
  fi

  # 1) 不足ビュー生成(右/後/左/上)。front は実画像をそのまま使う。
  need=()
  for v in right back left top; do [[ -f "$pdir/$v.png" ]] || need+=("$v"); done
  if [[ ${#need[@]} -gt 0 ]]; then
    echo "  ビュー生成: ${need[*]}"
    bash "$SCRIPT_DIR/gen_views.sh" "$front" "$pdir" "$SUBJECT の $name パーツ" "${need[@]}" >/dev/null 2>&1 || echo "  WARN: 一部ビュー生成失敗"
  fi

  # 2) 低ポリ化(ゲーム向け)
  "$BLENDER" --background --python "$SCRIPT_DIR/decimate.py" -- --mesh "$cloud" --out "$pdir/dec_uv.glb" --faces "$TRIS" >/dev/null 2>&1 \
    || { echo "  decimate失敗→cloud使用"; cp "$cloud" "$pdir/dec_uv.glb"; }

  # 3) UV投影ベイク
  python "$SCRIPT_DIR/uv_bake_part.py" --mesh "$pdir/dec_uv.glb" --views "$pdir" \
      --out "$pdir/model_uv.glb" --atlas "$pdir/atlas.png" --front-axis +z --cell "$CELL" \
    || { echo "  UVベイク失敗"; continue; }

  # 4) (任意) Codexでアトラス清書 → 同レイアウトのまま再適用
  if [[ "$CLEAN" == "1" ]]; then
    echo "  Codex清書..."
    codex exec -m gpt-5.5 -i "$pdir/atlas.png" --sandbox workspace-write --dangerously-bypass-approvals-and-sandbox \
"${PRE}

これは3Dモデルのテクスチャアトラスです。3列×2行のグリッドに、ある建物パーツ($SUBJECT の $name)を各方向(左上=正面,中上=右,右上=背面,左下=左,中下=上面,右下=下面)から見た正射図が並んでいます。
このアトラスを次の条件で清書してください:
- グリッドの分割位置・各セル内の絵の位置・スケール・構図を1ピクセルも動かさない(UVと一致させるため厳守)。
- 各セルの素材感(石垣・漆喰・木部・瓦・金箔等)をくっきり鮮明・継ぎ目なく整え、ノイズや白背景の残りを周囲の素材で自然に埋める。
- 灰色一色のセル(上面/下面など情報の無い面)は、その建物パーツを真上/真下から見た妥当な見た目(瓦屋根の俯瞰等)で描く。背景は単色グレー(#8a8a8a)。
- 出力は入力と同じ3列×2行・同じ縦横比のPNG。「$pdir/atlas_clean.png」に保存し、パスのみ報告。" \
      >/dev/null 2>&1 || echo "  WARN: Codex清書失敗"
    if [[ -f "$pdir/atlas_clean.png" ]]; then
      python "$SCRIPT_DIR/uv_bake_part.py" --mesh "$pdir/dec_uv.glb" --views "$pdir" \
          --out "$pdir/model_uv.glb" --atlas "$pdir/atlas_used.png" --front-axis +z --cell "$CELL" \
          --atlas-in "$pdir/atlas_clean.png" \
        && echo "  清書を再適用" || echo "  WARN: 再適用失敗(ベイク版を使用)"
    fi
  fi
  echo "  $name OK (tris=$TRIS)"
done
echo "UVテクスチャ完了: $PARTS_DIR"
