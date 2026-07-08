#!/usr/bin/env bash
# TripoSR をローカル(Apple Silicon / MPS)で実行し、画像から3Dメッシュ(形状)を生成する。
# 有料APIは一切使わない。出力は --out で指定したディレクトリに mesh.obj / mesh.glb を書く。
#
# 使い方:
#   run_triposr.sh --image <画像パス> [--image <画像2> ...] --out <出力ディレクトリ> \
#                  [--mc-resolution 256] [--no-remove-bg] [--device mps|cpu]
#
# 複数画像を渡した場合、TripoSR は各画像から1メッシュを作るため、
# 代表(最初=正面)を mesh.obj/mesh.glb とし、他は view_N.obj として残す。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIPOSR_DIR="$SCRIPT_DIR/TripoSR"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"

IMAGES=()
OUT=""
MC_RES="256"
REMOVE_BG="1"
DEVICE="mps"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGES+=("$2"); shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --mc-resolution) MC_RES="$2"; shift 2 ;;
    --no-remove-bg) REMOVE_BG="0"; shift 1 ;;
    --device) DEVICE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ ${#IMAGES[@]} -eq 0 || -z "$OUT" ]]; then
  echo "ERROR: --image と --out は必須です" >&2
  exit 2
fi

# 後で TripoSR ディレクトリへ cd するため、画像と出力先を絶対パスへ正規化する。
abspath() {
  local p="$1"
  if [[ "$p" = /* ]]; then echo "$p"; else echo "$(pwd)/$p"; fi
}
ABS_IMAGES=()
for img in "${IMAGES[@]}"; do
  ABS_IMAGES+=("$(abspath "$img")")
done
IMAGES=("${ABS_IMAGES[@]}")
OUT="$(abspath "$OUT")"

mkdir -p "$OUT"

# conda 環境を有効化
# shellcheck disable=SC1090
source "$CONDA_SH"
conda activate "$ENV_NAME"

# MPS のフォールバックを許可(未実装opをCPUで処理)
export PYTORCH_ENABLE_MPS_FALLBACK=1

# rembg(numba)/matplotlib が書き込むキャッシュを、書き込み可能な出力先配下に固定する。
# (Codex サンドボックス下で既定キャッシュ位置への書き込みが拒否されるのを防ぐ)
# 注意: XDG_CACHE_HOME は変更しない(huggingface のモデルキャッシュ位置がズレて再DLになるため)。
export NUMBA_CACHE_DIR="$OUT/.cache/numba"
export MPLCONFIGDIR="$OUT/.cache/mpl"
mkdir -p "$NUMBA_CACHE_DIR" "$MPLCONFIGDIR"

EXTRA=()
[[ "$REMOVE_BG" == "0" ]] && EXTRA+=("--no-remove-bg")

cd "$TRIPOSR_DIR"

echo "[run_triposr] device=$DEVICE mc_resolution=$MC_RES images=${#IMAGES[@]}"

# TripoSR 実行。OBJ 形式で出力(後段の Blender テクスチャ適用がしやすい)。
python run.py "${IMAGES[@]}" \
  --device "$DEVICE" \
  --mc-resolution "$MC_RES" \
  --model-save-format obj \
  --output-dir "$OUT/_tsr" \
  ${EXTRA[@]+"${EXTRA[@]}"}

# TripoSR は出力先に 0/、1/ ... と連番ディレクトリを作り mesh.obj を置く。
# 0 番(=最初に渡した画像=正面)を代表メッシュにする。
if [[ -f "$OUT/_tsr/0/mesh.obj" ]]; then
  cp "$OUT/_tsr/0/mesh.obj" "$OUT/mesh.obj"
  # 連番の各 view も残す
  i=0
  while [[ -f "$OUT/_tsr/$i/mesh.obj" ]]; do
    cp "$OUT/_tsr/$i/mesh.obj" "$OUT/view_$i.obj"
    i=$((i+1))
  done
  echo "[run_triposr] OK -> $OUT/mesh.obj (views=$i)"
else
  echo "ERROR: mesh.obj が生成されませんでした" >&2
  exit 1
fi
