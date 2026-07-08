#!/usr/bin/env bash
# ModelMaker3D の形状生成エンジン(TripoSR)をローカルにセットアップする。
# 有料APIは使わない。conda(miniconda)が必要。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_BASE="/opt/homebrew/Caskroom/miniconda/base"
CONDA_SH="$CONDA_BASE/etc/profile.d/conda.sh"
ENV_NAME="triposr311"

echo "==> ModelMaker3D エンジンセットアップ開始"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "✗ conda が見つかりません: $CONDA_SH" >&2
  echo "  miniconda をインストールしてください: brew install --cask miniconda" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CONDA_SH"

# 1) conda env (python 3.11)
if ! conda env list | grep -q "$ENV_NAME"; then
  echo "==> conda env '$ENV_NAME' を作成 (python 3.11)"
  conda create -y -n "$ENV_NAME" python=3.11
else
  echo "==> conda env '$ENV_NAME' は既に存在"
fi
conda activate "$ENV_NAME"

# 2) TripoSR を clone
if [[ ! -d "$SCRIPT_DIR/TripoSR/.git" && ! -f "$SCRIPT_DIR/TripoSR/run.py" ]]; then
  echo "==> TripoSR を clone"
  git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git "$SCRIPT_DIR/TripoSR"
fi

# 3) 依存をインストール (torchmcubes の代わりに PyMCubes を使う)
echo "==> 依存をインストール"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt"

# 4) TripoSR の isosurface を PyMCubes 版に差し替え (このリポジトリ同梱の patch)
#    ※ clone 直後は torchmcubes を import するため、同梱済みの差し替え版で上書きする。
if [[ -f "$SCRIPT_DIR/patches/isosurface.py" ]]; then
  cp "$SCRIPT_DIR/patches/isosurface.py" "$SCRIPT_DIR/TripoSR/tsr/models/isosurface.py"
  echo "==> isosurface.py を PyMCubes 版へ差し替え"
fi
if [[ -f "$SCRIPT_DIR/patches/run.py" ]]; then
  cp "$SCRIPT_DIR/patches/run.py" "$SCRIPT_DIR/TripoSR/run.py"
  echo "==> run.py を xatlas 遅延 import 版へ差し替え"
fi

# 5) モデルの事前ダウンロード(TripoSR 本体 + rembg u2net)
echo "==> モデルを事前ダウンロード (TripoSR 本体)"
export PYTORCH_ENABLE_MPS_FALLBACK=1
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("stabilityai/TripoSR")
print("TripoSR model ready")
PY

echo "==> rembg(u2net)モデルを事前ダウンロード"
mkdir -p "$HOME/.u2net"
if [[ ! -f "$HOME/.u2net/u2net.onnx" ]]; then
  curl -fL --retry 3 -o "$HOME/.u2net/u2net.onnx" \
    https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx
fi

echo "==> セットアップ完了。Blender (テクスチャ適用) は /Applications/Blender.app を使用します。"
echo "    動作テスト: bash $SCRIPT_DIR/run_triposr.sh --image $SCRIPT_DIR/TripoSR/examples/chair.png --out /tmp/tsr_test --device mps"
