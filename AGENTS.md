<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# ModelMaker3D 固有ルール

画像 / 複数視点 / テキスト から 3Dモデル(GLB・FBX)を生成するローカルツール。

## 役割分担(重要)

- **形状(ジオメトリ)**: ローカルの **TripoSR** を `engine/run_triposr.sh` 経由で実行(Apple Silicon / MPS)。
  AIメッシュ生成はこれだけ外部モデルが必要 = ただし無料のローカル実行。
- **テクスチャ**: **Codex 自身の画像生成ツール(image_gen)** で作成する。
- **後処理**: **Blender** (`engine/apply_texture.py`) でテクスチャをメッシュに適用し GLB / FBX を書き出す。

## 絶対ルール

- **有料 API キー (OPENAI_API_KEY, GEMINI_API_KEY, FAL_KEY 等) は使用禁止。** `.env` も作らない。
- 画像生成は Codex 自身の image_gen ツールで行う。HTTP / curl で画像生成 API を叩かない。
- 出力はジョブの cwd 直下にフラットに置く(`model.glb`, `model.fbx`, `mesh.obj`, `texture.png`, `input_*.png`, `manifest.json`)。
- 最後に必ず `manifest.json` を書き出す。`model.glb` は必ず存在させる。

## 構成

- `app/api/image-to-3d` / `app/api/multiview-to-3d` / `app/api/text-to-3d` … ジョブ作成 + Codex ストリーミング(SSE)
- `lib/prompt3d.ts` … Codex への作業指示(形状→テクスチャ→適用→manifest)
- `lib/runJob.ts` … Codex app-server を1ターン回して進捗をSSE配信
- `lib/blender.ts` … Node から Blender / 複数視点投影を直接実行するフォールバック(Codex サンドボックスで Blender がクラッシュする場合用)
- `engine/run_triposr.sh` … TripoSR ランナー(conda env: triposr311)
- `engine/apply_texture.py` … Blender テクスチャ適用 + GLB/FBX 書き出し
- `engine/run_multiview.sh` / `engine/project_multiview.py` … 複数視点の実写真をメッシュに投影(頂点カラー)
- `engine/setup.sh` … エンジン一括セットアップ(`npm run setup-engine`)

## 複数視点モード(本格対応)

- 形状は「正面」画像から TripoSR で生成。見た目は各方向(front/right/back/left/top/bottom)の実写真を
  `project_multiview.py` でメッシュに投影し頂点カラーとして焼く。テクスチャの画像生成は不要(実写真を使う)。
- Blender は Codex サンドボックス下でクラッシュしうるため、各ルートの finalize で Node 側から
  投影/Blender を実行するフォールバックを持つ。`model.glb` は必ず用意する。

## 本物UVテクスチャ(推奨・頂点カラーより鮮明 / ゲーム素材向け低ポリ)

頂点カラーは色の解像度がポリ数に依存しボケる。代わりに「キューブ投影UV + 投影ベイク」で
解像度がポリ数に依存しない2Dテクスチャ(アトラス)を作る。低ポリでも鮮明=ゲーム素材向け。

- `engine/uv_bake_part.py` … メッシュに各面の支配軸でキューブ投影UVを付け、各方向画像を
  3列×2行の「6面正射図グリッド」アトラスに焼く。`--atlas-in` で完成アトラスの再適用(Codex清書後)も可能。
  向き規約は project_multiview と同じ(front=+Z, up=+Y)。頂点は面ごとに分離(unmerge)して継ぎ目UVを確保。
- `engine/uv_texture_parts.sh <parts_dir>` … パーツ毎に [低ポリ化(decimate) → 不足ビュー生成(gen_views) →
  uv_bake_part] を回す。`--tris N`(既定12000, 目安5k〜15k) `--clean`(Codexでアトラス清書=AI仕上げ)
  `--clean-only`(既存atlasの清書+再適用のみ)。出力: parts/<name>/model_uv.glb, atlas.png。
- アトラス(atlas.png)は「綺麗で塗りやすいUVテクスチャ」そのもの。手で塗り直して
  `uv_bake_part.py --atlas-in <塗り直し.png>` で再適用できる(手編集ワークフロー)。
- 統合は `assemble.py --model-name model_uv.glb --no-join 1`(パーツ分離=手動編集向け)
  `--square-depth 0.9`(正面1枚由来で奥行が浅くなる対策: 奥行=幅×0.9 の正方形寄せ)。
- make3d_parts.sh は既定でこの低ポリUVテクスチャ + 分離統合を行う(`--clean`でAI仕上げ, `--tris`でポリ数)。

### 有機的キャラ/動物は「マルチビュー・ブレンド方式」(Meshy的・キューブ投影より高品質)
キューブ投影(1面=1ビュー)は腕/曲面/隠れ面でズレ・歪み・誤ブリードが出る。キャラは次を使う:
- `engine/smart_uv.py` … Smart UV展開(ヘッドレス可)。
- `engine/uv_bake_multiview.py` … 各テクセルを3D位置・法線に復元→**全ビューを法線重みでブレンド**→
  **深度バッファで隠れ面を除外(オクルージョン)**→未塗りインペイント。`--front-axis +z --size 2048 --power 3`。
- `engine/stand_smooth.py` … TripoSRの横倒しを立て、溶接+スムーズ化(uv_bakeは up=+Y/front=+Z 前提)。
- 入口: `engine/make3d_character.sh`(=`make3d.sh character <正面> [<横> <後ろ>]`)が
  TripoSR→stand_smooth→不足ビュー生成→smart_uv→uv_bake_multiview→Mixamo用FBX まで全自動。
