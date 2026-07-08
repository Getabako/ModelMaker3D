# ModelMaker3D

画像 / 複数視点 / テキスト から **3Dモデル(GLB・FBX)** を生成するローカルツール。
Tripo3D・Meshy のような「AIで3Dモデリング」を、**有料APIを使わず**ローカル＋Codexサブスクで実現する。

- **形状(ジオメトリ)**: ローカルの **TripoSR**(Apple Silicon / MPS)で生成 — 無料・ローカル
- **テクスチャ**: **Codex の画像生成(image_gen)** で作成 — サブスク、有料画像APIは不使用
- **後処理**: **Blender** でテクスチャを貼って GLB / FBX を書き出し
- **プレビュー**: ブラウザ上で `<model-viewer>` による 3D プレビュー + ダウンロード

## できること

| モード | 入力 | 出力 |
|--------|------|------|
| 画像→3D | 正面1枚の画像 | テクスチャ付き GLB / FBX(テクスチャは Codex 画像生成) |
| 複数視点→3D | 正面・横・後ろ など複数画像 | 全方向に実写真を投影した頂点カラー GLB / FBX |
| テキスト→3D | 文章(例: 「木製の椅子」) | コンセプト画像→GLB / FBX |

### 複数視点→3D の仕組み(本格対応)

形状は「正面」画像から TripoSR で生成し、**見た目は正面/右横/後ろ/左横/上/下の実写真をメッシュへ投影**して
頂点カラーとして焼き込む(`engine/project_multiview.py`)。各頂点は、その面を最もよく向いているビューの
写真の色を採用する。実写真をそのまま使うため、単画像生成テクスチャより忠実。
出来上がりの前後左右がズレる場合は UI の「形状の向き補正」(`--front-axis`)で調整する。

> 注: 形状そのものは正面画像由来(TripoSR は単画像モデル)。複数写真は主に全方向の見た目に使う。
> 真の多視点ジオメトリ融合は将来 Hunyuan3D-mv 等のマルチビュー対応モデルで拡張可能。

## 起動(スキル)

Claude Code / Codex で `/modelmaker3d` を実行すると、ビルド確認のうえブラウザで自動起動する。

## ターミナル直叩き(UI不要・ワンコマンド)

このフォルダで Claude Code / Codex に画像パスや作りたいものを伝えるだけで、UIを立ち上げずに生成できる
(`engine/make3d.sh`)。Claude には CLAUDE.md でこの動作を指示済み。手動でも実行可能:

```bash
# 画像→3D(入力画像の色をそのまま使う・完全ローカル)
bash engine/make3d.sh image path/to/photo.png [--fbx]

# 複数視点→3D(実写真を全方向に投影)
bash engine/make3d.sh multiview front=f.png right=r.png back=b.png left=l.png [--fbx]

# テキスト→3D(Codexサブスクでコンセプト画像生成→立体化)
bash engine/make3d.sh text "木製の椅子" [--fbx]

# クラウド高品質(Colab Pro の Hunyuan3D-2)。複雑な建築・メカ向け
bash engine/make3d.sh cloud path/to/image.png [--fbx]
```

出力: `generated/<時刻>/model.glb`(+ `mesh.obj`、`--fbx` 指定時は `model.fbx`)。
オプション: `--out <DIR>` / `--res 256`(128〜320) / `--axis +z`(向き補正)。

## クラウド高品質モード(Colab Pro / Hunyuan3D-2)

TripoSR は「フィギュア・小物・家具・キャラ」などコンパクトな単一物体は得意だが、
多層建築(城など)や細かいメカは苦手。そういう対象は **Colab Pro の GPU で Hunyuan3D-2** を使う。
生成ごとの従量課金API ではなく Colab サブスクの GPU を使う。

セットアップ(初回):
1. `colab/ModelMaker3D_Cloud.ipynb` を Colab で開き、GPUランタイム(A100/L4)で上から実行。
2. 最後のセルが出す公開URL(`https://xxxx.trycloudflare.com`)を Mac に保存:
   ```bash
   echo 'https://xxxx.trycloudflare.com' > ~/.modelmaker3d_cloud
   ```
3. Colab のセルは実行したまま開いておく。

以降は Mac で `bash engine/make3d.sh cloud path/to/image.png`。
テクスチャ生成(paint)が Colab で有効ならテクスチャ付き、無効なら形状を受け取り入力画像を投影して色付けする。

## セットアップ

前提: macOS (Apple Silicon)、`codex` CLI、miniconda、Blender(`/Applications/Blender.app`)。

```bash
# 1) 形状エンジン(TripoSR / conda env: triposr311)をセットアップ(初回のみ・モデルDLあり)
npm run setup-engine

# 2) Web UI の依存をインストール & ビルド
npm install
npm run build

# 3) 起動(ブラウザが localhost:4573 で開く)
npm start
```

開発時は `npm run dev`。

## 仕組み

1. UI から画像/テキストを送信 → API がジョブ用フォルダ(保存先/ジョブID)を作成
2. **Codex app-server** がそのフォルダを cwd にして作業を実行(`lib/prompt3d.ts` の指示)
   - `engine/run_triposr.sh` を実行して **mesh.obj**(形状)を生成
   - **image_gen** で **texture.png**(テクスチャ)を生成
   - `engine/apply_texture.py`(Blender)で **model.glb / model.fbx** を書き出し
   - **manifest.json** を書いて完了
3. 進捗は SSE でリアルタイム表示、完了後にブラウザで 3D プレビュー

## 注意

- 有料 API(OpenAI Images / DALL·E, Gemini, Fal.ai 等)は一切使わない。
- 形状生成は初回にモデル(約1.6GB)と rembg(約176MB)をダウンロードする。
- TripoSR 本体は `engine/TripoSR/`(git 管理外)。PyMCubes 版への差し替えは `engine/patches/` から `setup.sh` が適用する。

## ライセンス

TripoSR は MIT(VAST AI Research)。本ツールのラッパー部分は社内利用想定。
