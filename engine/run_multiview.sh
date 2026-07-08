#!/usr/bin/env bash
# 複数視点の実写真をメッシュに投影して頂点カラー付き GLB を作る(project_multiview.py)。
# conda env: triposr311 を有効化して実行する。有料APIは使わない。
#
# 使い方:
#   run_multiview.sh --mesh <mesh.obj> --out <model.glb> \
#       --view front=<path> --view right=<path> --view back=<path> --view left=<path> \
#       [--view top=<path>] [--view bottom=<path>] [--front-axis +z]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"

# shellcheck disable=SC1090
source "$CONDA_SH"
conda activate "$ENV_NAME"

python "$SCRIPT_DIR/project_multiview.py" "$@"
