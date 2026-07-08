@AGENTS.md

## ターミナルで直接指示されたときの動作(最重要・他Maker同様)

このフォルダで Claude Code / Codex を開き、ユーザーが**画像のパス**や**作りたいものの説明**を渡して
「3Dモデルにして」等と言ったら、**Web UI を起動せず、その場で `engine/make3d.sh` を実行して成果物を作り切る**。
確認は不要。完成したら `model.glb`(必要なら FBX)のパスを数行で報告する。

判定と実行(これだけでよい):

- **画像のパスを渡された** → 画像→3D(入力画像の色をそのまま使う・完全ローカル):
  ```bash
  bash engine/make3d.sh image "<画像パス>" [--fbx]
  ```
- **複数の画像(正面/横/後ろ等)を渡された** → 複数視点→3D(実写真を全方向に投影):
  ```bash
  bash engine/make3d.sh multiview front="<正面>" right="<右>" back="<後ろ>" left="<左>" [top="<上>"] [--fbx]
  ```
- **テキスト(作りたいもの)だけ渡された** → テキスト→3D(Codexサブスクでコンセプト画像生成→立体化):
  ```bash
  bash engine/make3d.sh text "<作りたいもの>" [--fbx]
  ```
- **人型/動物キャラ(正面[+横+後ろ])を渡された** → キャラ専用パイプライン(高品質既定):
  ```bash
  bash engine/make3d.sh character "<正面>" ["<横>" "<後ろ>"] --subject "<説明>"
  ```
  立て直し・**顔の正面自動整列**・頂点溶接・スムーズ化・頭頂ビュー生成・背景インペイント・手足補正・正面軸+z を**毎回自動適用**し、
  `model_uv.glb`(確認用)と `for_mixamo.fbx`(Mixamo用)を出力。リグは Mixamo(手動マーカー)。
  - **向き補正は毎回自動**: TripoSRの既定の向き(ヨー)はキャラごとにズレるが、`stand_smooth.py` が
    腕幅を左右(X)に・顔を正面(-Y=Blender正面ビュー/glTF +Z)へ自動整列してから焼くので、テクスチャが
    側面に回り込む不具合は解消済み。正面判定はつま先=前/後頭部=後ろのヒューリスティック。
  - 自動判定を誤ったとき(顔が横/後ろを向く)だけ `--face` で上書き: 現在の顔向き軸を指定する。
    例 `--face +x`(顔が+Xを向いている) / `-x` / `+y` / `-y` / `keep`(整列しない)。

オプション: `--out <DIR>`(既定 `generated/<時刻>`)、`--res 256`(細かさ128〜320)、`--axis +z`(向き補正)、
`--fbx`(FBXも出力)、`--usdz`(Procreate用USDZも出力)。

- **Procreateで編集したい / iPadで塗りたい** と言われたら、USDZ(自己完結・テクスチャ同梱)で出す:
  - 生成と同時に: 上記モードに `--usdz` を付ける(`character` は常に `model.usdz` も出力)
  - 既存モデルを変換: `bash engine/make3d.sh usdz "<model.glb/fbx/obj>" [--out DIR]`
  - 中身は `*.usdc` + 同梱テクスチャのみ(背景色exrは出さない=Procreate白対策済み)。`engine/export_usdz.py` が本体。

- **複雑な対象(建築・メカ等)で TripoSR の品質が足りない場合** → クラウド(Colab Pro の Hunyuan3D-2):
  ```bash
  bash engine/make3d.sh cloud "<画像パス>" [--fbx]
  ```
  事前に Colab で `colab/ModelMaker3D_Cloud.ipynb` を実行し、表示された公開URLを
  `~/.modelmaker3d_cloud` に保存しておく(または `--endpoint <URL>`)。Colabのセルは実行したまま開いておく。

## テクスチャ作成の既定方針(重要・常時)

3Dの色付けは **正面1枚で終わらせない**。常に **横(right/left)・後ろ(back)等の不足ビューを Codex で生成して全周投影**する
(`engine/gen_views.sh` で生成 → `engine/run_multiview.sh` で投影)。`make3d.sh cloud` は既定でこれを行う
(`--subject "<対象説明>"` を付けると生成ビューの精度が上がる。正面のみにしたい時だけ `--no-auto-views`)。
- 投影画像はパース無しの平行投影風(真正面/真横/真後ろ)を使う。斜めパース画像を平行投影で貼るとズレる。
- 最良は A100/L4 GPU で Colab `ENABLE_PAINT=True`(Hunyuan3Dが本物UVテクスチャを全周生成)。T4等で使えない時に全周ビュー投影を既定フォールバックにする。
- 既存メッシュに色だけ貼り直す場合: `bash engine/gen_views.sh <正面> <DIR> "<説明>" right back left` → `bash engine/run_multiview.sh --mesh <mesh> --out <DIR>/model.glb --view front=<正面> --view right=... --view back=... --view left=...`

補足:
- 形状は TripoSR をローカル実行(MPS)。`make3d.sh` が形状→色付け→GLB(必要なら FBX)まで一括で行う。
- TripoSR の image モードは NeRF 由来の頂点カラーで全周に色が付くため、追加ビュー生成は不要(cloud/投影系で必要)。
- 画像/複数視点はテクスチャに**実画像**を使うため画像生成は不要。テキストのときだけ Codex の画像生成を使う(有料画像APIは禁止)。
- うまく形が出ない時は `--res` を上げる、向きが変な時は `--axis -z`/`+x`/`-x` を試す。
- TripoSR はフィギュア/小物/家具/キャラなど**コンパクトな単一物体**が得意。多層建築など複雑形状は `cloud` モード(Hunyuan3D-2)を使う。
- **複雑建築をローカル(image/text)で頼まれた場合**: まず生成を試しつつ、結果が崩れやすいことを伝え、`cloud` モードを提案する。

## セットアップ

形状エンジン(TripoSR / conda env: triposr311)が未構築なら最初に:
```bash
npm run setup-engine
```
