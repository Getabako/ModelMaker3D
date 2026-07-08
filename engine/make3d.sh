#!/usr/bin/env bash
# ModelMaker3D ワンショットCLI — ターミナルで直接3Dモデルを作る。
# Web UI も Codex app-server も不要。形状はローカルTripoSR、有料APIは使わない。
#
# 使い方:
#   make3d.sh image    <画像パス>           [--out DIR] [--res 256] [--axis +z] [--fbx]
#   make3d.sh multiview --out DIR [--res N] [--axis +z] [--fbx] front=<p> right=<p> back=<p> left=<p> [top=<p>] [bottom=<p>]
#   make3d.sh text     "<作りたいもの>"     [--out DIR] [--res 256] [--fbx]
#   make3d.sh cloud    <画像パス>           [--endpoint URL] [--out DIR] [--axis +z] [--fbx] [--steps 50] [--octree 384]
#   make3d.sh character <正面> [<横> <後ろ>] [--out DIR] [--subject "説明"]  (人型/動物: Mixamo用FBXまで)
#   make3d.sh usdz     <model.glb>          [--out DIR]                      (既存モデルをProcreate用USDZへ変換)
#
# 共通オプション: --fbx (FBXも出力) / --usdz (Procreate用USDZも出力)
# 出力: <DIR>/model.glb (+ mesh.obj, --fbx 時 model.fbx, --usdz 時 model.usdz)。DIR 既定は ./generated/<時刻>。
#
# - image:     入力画像の色をそのまま頂点カラーに使う(画像生成不要・完全ローカル・TripoSR)。
# - multiview: 正面から形状を作り、各方向の実写真をメッシュに投影(TripoSR)。
# - text:      Codexサブスクの画像生成でコンセプト画像を作ってから image と同じ処理(TripoSR)。
# - cloud:     Colab(Hunyuan3D-2)の公開エンドポイントに画像を送り高品質メッシュを得る。
#              複雑な建築など TripoSR が苦手な対象向け。Colab Pro の GPU を使う(サブスク)。
#              エンドポイントは --endpoint / 環境変数 MODELMAKER_CLOUD_URL / ~/.modelmaker3d_cloud の順で解決。
#              L4/A100(Colab Pro)では本物UVテクスチャ(paint)が返る。--steps=品質(既定50) --octree=精細度(256/384/512)。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
ENV_NAME="triposr311"
BLENDER="${BLENDER_PATH:-/Applications/Blender.app/Contents/MacOS/Blender}"

MODE="${1:-}"; shift || true
[[ -z "$MODE" ]] && { echo "ERROR: モードを指定してください (image|multiview|text)" >&2; exit 2; }

OUT=""
RES="256"
AXIS="+z"
WANT_FBX="0"
WANT_USDZ="0"
ENDPOINT=""
SUBJECT=""
STEPS="50"
OCTREE="384"
FACE="auto"
NO_AUTO_VIEWS="0"
POSITIONAL=()
VIEWS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --res) RES="$2"; shift 2 ;;
    --axis) AXIS="$2"; shift 2 ;;
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --steps) STEPS="$2"; shift 2 ;;
    --octree) OCTREE="$2"; shift 2 ;;
    --subject) SUBJECT="$2"; shift 2 ;;
    --face) FACE="$2"; shift 2 ;;
    --no-auto-views) NO_AUTO_VIEWS="1"; shift 1 ;;
    --fbx) WANT_FBX="1"; shift 1 ;;
    --usdz) WANT_USDZ="1"; shift 1 ;;
    front=*|right=*|back=*|left=*|top=*|bottom=*) VIEWS+=("$1"); shift 1 ;;
    *) POSITIONAL+=("$1"); shift 1 ;;
  esac
done

abspath() { local p="$1"; if [[ "$p" = /* ]]; then echo "$p"; else echo "$(pwd)/$p"; fi; }

if [[ -z "$OUT" ]]; then
  TS="$(date +%Y%m%d-%H%M%S)"
  OUT="$(pwd)/generated/$TS"
fi
OUT="$(abspath "$OUT")"
mkdir -p "$OUT"

# shellcheck disable=SC1090
source "$CONDA_SH"
conda activate "$ENV_NAME"

run_geo() {  # $1=image path
  bash "$SCRIPT_DIR/run_triposr.sh" --image "$1" --out "$OUT" --mc-resolution "$RES" --device mps
}

to_glb_from_obj() {
  python "$SCRIPT_DIR/obj_to_glb.py" "$OUT/mesh.obj" "$OUT/model.glb"
}

maybe_fbx() {  # $1 = source mesh for fbx (glb)
  [[ "$WANT_FBX" != "1" ]] && return 0
  if [[ -x "$BLENDER" || -f "$BLENDER" ]]; then
    "$BLENDER" --background --python "$SCRIPT_DIR/apply_texture.py" -- \
      --mesh "$1" --out "$OUT/_fbxtmp.glb" --fbx "$OUT/model.fbx" || \
      echo "[make3d] FBX 書き出しに失敗(GLBはあります)。スキップ。" >&2
    rm -f "$OUT/_fbxtmp.glb"
  else
    echo "[make3d] Blender が見つからないため FBX はスキップ。" >&2
  fi
}

maybe_usdz() {  # $1 = source mesh (glb) -> Procreate 用 USDZ
  [[ "$WANT_USDZ" != "1" ]] && return 0
  if [[ -x "$BLENDER" || -f "$BLENDER" ]]; then
    "$BLENDER" --background --python "$SCRIPT_DIR/export_usdz.py" -- \
      --mesh "$1" --out "$OUT/model.usdz" 2>&1 | grep -iE "export_usdz|ERROR" || \
      echo "[make3d] USDZ 書き出しに失敗(GLBはあります)。スキップ。" >&2
  else
    echo "[make3d] Blender が見つからないため USDZ はスキップ。" >&2
  fi
}

case "$MODE" in
  usdz)
    # 既存モデル(glb/fbx/obj)を Procreate 用 USDZ に変換するだけのモード。
    # 使い方: make3d.sh usdz <model.glb> [--out DIR]
    [[ ${#POSITIONAL[@]} -lt 1 ]] && { echo "ERROR: 変換するモデル(glb/fbx/obj)を指定してください" >&2; exit 2; }
    SRC="$(abspath "${POSITIONAL[0]}")"
    [[ -f "$SRC" ]] || { echo "ERROR: モデルが見つかりません: $SRC" >&2; exit 1; }
    OUTFILE="$OUT/$(basename "${SRC%.*}").usdz"
    echo "[make3d] usdz モード: $SRC -> $OUTFILE"
    "$BLENDER" --background --python "$SCRIPT_DIR/export_usdz.py" -- \
      --mesh "$SRC" --out "$OUTFILE" 2>&1 | grep -iE "export_usdz|ERROR"
    echo "[make3d] 完成: $OUTFILE"
    exit $?
    ;;

  parts)
    # パーツ分割パイプライン(最高品質: 部品分解→部品ごと形状+本物UVテクスチャ→統合)。Colab(cloud)必須。
    # 使い方: make3d.sh parts <参照画像> --subject "<対象説明>" [--out DIR] [--tris N] [--clean] [--endpoint URL]
    [[ ${#POSITIONAL[@]} -lt 1 ]] && { echo "ERROR: 参照画像を指定してください" >&2; exit 2; }
    PF="$(abspath "${POSITIONAL[0]}")"
    PARGS=("$PF" --out "$OUT")
    [[ -n "$SUBJECT" ]] && PARGS+=("$SUBJECT")
    [[ -n "$ENDPOINT" ]] && PARGS+=(--endpoint "$ENDPOINT")
    echo "[make3d] parts モード: $PF"
    bash "$SCRIPT_DIR/make3d_parts.sh" "${PARGS[@]}"
    rc=$?
    [[ "$WANT_USDZ" == "1" && -f "$OUT/model.glb" ]] && maybe_usdz "$OUT/model.glb"
    exit $rc
    ;;

  character)
    # 人型/動物キャラ専用(高品質既定): 立て・溶接・スムーズ・top生成・背景インペイント・手足補正・正面軸+z を自動適用。
    # 使い方: make3d.sh character <正面> [<横> <後ろ>] [--out DIR] [--subject "説明"] [--no-mixamo] [--face auto|+x|-x|+y|-y|keep]
    # 顔の正面は毎回自動整列(--face auto)。誤判定時のみ --face で現在の顔向き軸を指定して上書き。
    [[ ${#POSITIONAL[@]} -lt 1 ]] && { echo "ERROR: 正面画像(必要なら横/後ろも)を指定してください" >&2; exit 2; }
    CF="$(abspath "${POSITIONAL[0]}")"
    CARGS=(--front "$CF" --out "$OUT" --face "$FACE" --res "$RES")
    [[ ${#POSITIONAL[@]} -ge 2 ]] && CARGS+=(--side "$(abspath "${POSITIONAL[1]}")")
    [[ ${#POSITIONAL[@]} -ge 3 ]] && CARGS+=(--back "$(abspath "${POSITIONAL[2]}")")
    [[ -n "$SUBJECT" ]] && CARGS+=("$SUBJECT")
    echo "[make3d] character モード: $CF"
    bash "$SCRIPT_DIR/make3d_character.sh" "${CARGS[@]}"
    exit $?
    ;;

  image)
    [[ ${#POSITIONAL[@]} -lt 1 ]] && { echo "ERROR: 画像パスを指定してください" >&2; exit 2; }
    IMG="$(abspath "${POSITIONAL[0]}")"
    [[ -f "$IMG" ]] || { echo "ERROR: 画像が見つかりません: $IMG" >&2; exit 1; }
    echo "[make3d] image モード: $IMG"
    cp "$IMG" "$OUT/input_0.png" 2>/dev/null || true
    run_geo "$IMG"
    to_glb_from_obj
    maybe_fbx "$OUT/model.glb"
    maybe_usdz "$OUT/model.glb"
    ;;

  multiview)
    [[ ${#VIEWS[@]} -lt 2 ]] && { echo "ERROR: front=... right=... の形式で2つ以上のビューを指定してください" >&2; exit 2; }
    # front を探す(無ければ最初のビュー)
    FRONT=""
    for v in "${VIEWS[@]}"; do [[ "$v" == front=* ]] && FRONT="$(abspath "${v#front=}")"; done
    [[ -z "$FRONT" ]] && FRONT="$(abspath "${VIEWS[0]#*=}")"
    [[ -f "$FRONT" ]] || { echo "ERROR: 正面画像が見つかりません: $FRONT" >&2; exit 1; }
    echo "[make3d] multiview モード: front=$FRONT views=${#VIEWS[@]}"
    run_geo "$FRONT"
    MV_ARGS=()
    for v in "${VIEWS[@]}"; do
      name="${v%%=*}"; p="$(abspath "${v#*=}")"
      MV_ARGS+=(--view "$name=$p")
    done
    bash "$SCRIPT_DIR/run_multiview.sh" --mesh "$OUT/mesh.obj" --out "$OUT/model.glb" --front-axis "$AXIS" "${MV_ARGS[@]}"
    maybe_fbx "$OUT/model.glb"
    maybe_usdz "$OUT/model.glb"
    ;;

  text)
    [[ ${#POSITIONAL[@]} -lt 1 ]] && { echo "ERROR: 作りたいものをテキストで指定してください" >&2; exit 2; }
    PROMPT="${POSITIONAL[*]}"
    echo "[make3d] text モード: $PROMPT"
    if ! command -v codex >/dev/null 2>&1; then
      echo "ERROR: text モードはコンセプト画像生成に codex CLI が必要です" >&2; exit 1
    fi
    # Codexサブスクの画像生成でコンセプト画像を作る(有料画像APIは使わない)
    codex exec -m gpt-5.5 --sandbox workspace-write --dangerously-bypass-approvals-and-sandbox \
      "「${PROMPT}」を正面から見た1体だけ、背景は完全な単色グレー(#808080)、影や地面やテキストなしで描いてください。あなたの画像生成ツールで生成し、ファイルを ${OUT}/input_0.png に保存してください。完了したら保存パスのみ報告してください。"
    [[ -f "$OUT/input_0.png" ]] || { echo "ERROR: コンセプト画像が生成されませんでした: $OUT/input_0.png" >&2; exit 1; }
    run_geo "$OUT/input_0.png"
    to_glb_from_obj
    maybe_fbx "$OUT/model.glb"
    maybe_usdz "$OUT/model.glb"
    ;;

  cloud)
    [[ ${#POSITIONAL[@]} -lt 1 ]] && { echo "ERROR: 画像パスを指定してください" >&2; exit 2; }
    IMG="$(abspath "${POSITIONAL[0]}")"
    [[ -f "$IMG" ]] || { echo "ERROR: 画像が見つかりません: $IMG" >&2; exit 1; }
    # エンドポイント解決: --endpoint > 環境変数 > ~/.modelmaker3d_cloud
    [[ -z "$ENDPOINT" ]] && ENDPOINT="${MODELMAKER_CLOUD_URL:-}"
    [[ -z "$ENDPOINT" && -f "$HOME/.modelmaker3d_cloud" ]] && ENDPOINT="$(tr -d '[:space:]' < "$HOME/.modelmaker3d_cloud")"
    [[ -z "$ENDPOINT" ]] && { echo "ERROR: Colab の公開URLを指定してください(--endpoint、または ~/.modelmaker3d_cloud に保存)" >&2; exit 2; }
    echo "[make3d] cloud モード: $IMG -> $ENDPOINT"
    cp "$IMG" "$OUT/input_0.png" 2>/dev/null || true
    python "$SCRIPT_DIR/cloud_generate.py" --endpoint "$ENDPOINT" --image "$IMG" --out "$OUT/cloud_model.glb" --steps "$STEPS" --octree "$OCTREE" || {
      echo "ERROR: クラウド生成に失敗しました(Colabのセル/URLを確認してください)" >&2; exit 1; }
    # テクスチャ付きで返ってきたらそのまま、形状のみなら入力画像を正面投影して色付け
    TEXTURED="$(python -c "import json,sys;print(json.load(open('$OUT/cloud_model_meta.json')).get('textured',False))" 2>/dev/null || echo False)"
    if [[ "$TEXTURED" == "True" ]]; then
      cp "$OUT/cloud_model.glb" "$OUT/model.glb"
      cp "$OUT/cloud_model.glb" "$OUT/mesh.obj" 2>/dev/null || true
    elif [[ "$NO_AUTO_VIEWS" == "1" ]]; then
      echo "[make3d] 形状のみ受信 → 正面のみ投影(--no-auto-views)"
      bash "$SCRIPT_DIR/run_multiview.sh" --mesh "$OUT/cloud_model.glb" --out "$OUT/model.glb" --front-axis "$AXIS" --view front="$IMG" || \
        cp "$OUT/cloud_model.glb" "$OUT/model.glb"
    else
      # 既定: 不足ビュー(右/後ろ/左)を Codex で生成し、全周投影して色付け
      echo "[make3d] 形状のみ受信 → 横/後ろビューを生成して全周投影"
      SUBJ="${SUBJECT:-この対象}"
      bash "$SCRIPT_DIR/gen_views.sh" "$IMG" "$OUT" "$SUBJ" right back left || echo "[make3d] WARN: ビュー生成で一部失敗" >&2
      MV=(--view front="$IMG")
      for v in right back left; do [[ -f "$OUT/$v.png" ]] && MV+=(--view "$v=$OUT/$v.png"); done
      bash "$SCRIPT_DIR/run_multiview.sh" --mesh "$OUT/cloud_model.glb" --out "$OUT/model.glb" --front-axis "$AXIS" "${MV[@]}" || \
        cp "$OUT/cloud_model.glb" "$OUT/model.glb"
    fi
    maybe_fbx "$OUT/model.glb"
    maybe_usdz "$OUT/model.glb"
    ;;

  *)
    echo "ERROR: 未知のモード: $MODE (image|multiview|text|cloud|character|parts|usdz)" >&2; exit 2 ;;
esac

# 後始末(中間ファイル)
rm -rf "$OUT/_tsr" "$OUT/.cache" 2>/dev/null || true

echo ""
echo "=========================================="
echo "  完成: $OUT/model.glb"
[[ -f "$OUT/model.fbx" ]] && echo "  FBX : $OUT/model.fbx"
echo "  形状: $OUT/mesh.obj"
echo "=========================================="
