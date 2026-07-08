#!/usr/bin/env bash
# 参照画像を Codex で解析し、対象を「部品(パーツ)」に分解して parts.json を書き出す。
# パーツ分割パイプラインの最初のステップ。有料画像APIは使わず Codexサブスクを使う。
#
# 使い方:
#   decompose.sh <参照画像> <出力DIR> "<対象の説明>"
#
# 出力: <出力DIR>/parts.json
#   {
#     "subject": "...",
#     "parts": [
#       {"name":"stone_base","desc":"石垣の台座","cx":0.5,"cy":0.86,"w":0.96,"h":0.26,"depth":0.85,"order":0},
#       ...
#     ]
#   }
# 座標は画像左上原点の正規化(0-1)。cx,cy=中心、w,h=幅高さ、depth=前後の奥行き(おおよそ w 基準)、order=下から上の積み順。

set -euo pipefail

FRONT="${1:-}"; OUTDIR="${2:-}"; SUBJECT="${3:-対象}"
[[ -z "$FRONT" || -z "$OUTDIR" ]] && { echo "usage: decompose.sh <image> <outdir> <subject>" >&2; exit 2; }
[[ -f "$FRONT" ]] || { echo "ERROR: 画像が見つかりません: $FRONT" >&2; exit 1; }
command -v codex >/dev/null 2>&1 || { echo "ERROR: codex CLI が必要です" >&2; exit 1; }
mkdir -p "$OUTDIR"
OUTJSON="$OUTDIR/parts.json"

PRE="これは自動化されたジョブです。中央ナレッジベース確認・タスク報告等のセッション開始儀式は一切行わないでください。前置きや会話も不要。下記の作業だけを行い、最後にファイルを書き出してパスのみ報告してください。"

codex exec -m gpt-5.5 -i "$FRONT" --sandbox workspace-write --dangerously-bypass-approvals-and-sandbox \
"${PRE}

参照画像は「${SUBJECT}」です。これを3Dモデル化するために、**個別に作って後で統合できる部品(パーツ)**へ分解してください。
複雑な対象は1個の塊で作ると形が崩れるため、意味のある構造単位(例: 建築なら 石垣/各階の躯体/各層の屋根/望楼、 生き物なら 頭/胴/腕/脚 等)に分けます。

各パーツについて、参照画像を見て次を推定し、**厳密な JSON** を「${OUTJSON}」に書き出してください:
- name: 英数字スネークケースの識別子(例 stone_base, floor1_body, roof1, tower_top)
- desc: そのパーツ単体を画像生成するための日本語の説明(色・形・素材を含める)
- cx, cy: パーツ中心の正規化座標(画像左上を0,0、右下を1,1)
- w, h: パーツの正規化サイズ(0-1)
- depth: 前後方向のおおよその奥行き(0-1、正方形断面なら w と同程度、薄い壁なら小さく)
- order: 下から上/手前から奥への積み順を表す整数(小さいほど下/土台)

形式(コメントは入れない、有効なJSONのみ):
{
  \"subject\": \"${SUBJECT}\",
  \"parts\": [
    {\"name\":\"stone_base\",\"desc\":\"...\",\"cx\":0.5,\"cy\":0.86,\"w\":0.96,\"h\":0.26,\"depth\":0.85,\"order\":0}
  ]
}

パーツ数は対象の複雑さに応じて 4〜12 個程度。重なり/積み重なりも order と cy で表現してください。
${OUTJSON} に有効なJSONだけを書き出すこと。" \
  2>&1 | tail -5

if [[ -f "$OUTJSON" ]]; then
  echo "[decompose] OK -> $OUTJSON"
else
  echo "[decompose] ERROR: parts.json が生成されませんでした" >&2
  exit 1
fi
