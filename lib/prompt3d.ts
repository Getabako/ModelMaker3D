// Codex に渡す「3Dモデル生成ジョブ」の指示プロンプト。
// 役割分担:
//   - 形状(ジオメトリ): ローカルの TripoSR を実行(run_triposr.sh)。AIメッシュ生成はこれだけ外部モデルが要る=無料ローカル。
//   - テクスチャ: Codex 自身の画像生成ツール(image_gen)で作成。
//   - 後処理: Blender(apply_texture.py)でテクスチャをメッシュに適用し GLB / FBX 書き出し。
// 有料API(OpenAI Images, Gemini, Fal.ai 等)は一切使わない。

const JOB_PREAMBLE = `# 🤖 これは自動化された単発ジョブです(最優先)

- セッション開始時の儀式(中央ナレッジベース確認・タスク管理シート確認・本日のタスク報告・activity-log への記録 等)は **一切行わない**。
- 他のプロジェクトのファイルを読みに行かない。下記の cwd 内だけで作業する。
- 会話や前置きの説明は最小限。**下記の3D生成タスクだけ**を黙々と実行し、完了したら manifest.json を書いて終わる。
`;

const COMMON_RULES = (engineDir: string, blender: string, cwd: string) => `# 🚨 ツール使用ルール(絶対)

- 外部の有料 API キー (OPENAI_API_KEY, GEMINI_API_KEY, FAL_KEY 等) は **使用禁止**。\`.env\` も作らない。
- 画像(テクスチャ・コンセプト画像)の生成は **あなた(Codex)自身が持っている画像生成ツール(image_gen)** で行う。
  HTTP / curl で画像生成 API を叩かない。
- 形状生成は **ローカルの TripoSR** を下記スクリプトで実行する(これは無料のローカル実行)。
- すべての出力は cwd 直下に書く: \`${cwd}\`
- 作業はすべてあなた(Codex)が実行する。最後に必ず \`manifest.json\` を書き出して終了する。

# 環境
- ENGINE_DIR(スクリプト置き場): \`${engineDir}\`
- TripoSR ランナー: \`bash ${engineDir}/run_triposr.sh\`
- Blender テクスチャ適用: \`${blender} --background --python ${engineDir}/apply_texture.py --\`
- 作業ディレクトリ(cwd): \`${cwd}\``;

const GEOMETRY_STEP = (cwd: string, engineDir: string, images: string[], mcResolution: number) => {
  const imgArgs = images.map((p) => `--image "${p}"`).join(" ");
  return `# 手順1: 形状(ジオメトリ)を生成する

次のコマンドを実行して、入力画像から3Dメッシュ(\`${cwd}/mesh.obj\`)を生成する:

\`\`\`bash
bash "${engineDir}/run_triposr.sh" ${imgArgs} --out "${cwd}" --mc-resolution ${mcResolution} --device mps
\`\`\`

- 成功すると \`${cwd}/mesh.obj\`(代表メッシュ=正面画像由来)が作られる。複数画像なら \`view_0.obj, view_1.obj ...\` も残る。
- エラーが出たら \`--device cpu\` で再試行する。
- \`mesh.obj\` が生成されたことを必ず確認してから次へ進む。`;
};

const TEXTURE_STEP = (cwd: string, subjectDesc: string, uvMode: string) => `# 手順2: テクスチャ画像を生成する(あなたの image_gen ツールで)

\`${cwd}/texture.png\` というテクスチャ画像を **あなた自身の画像生成ツール** で作成する。

対象: ${subjectDesc}

テクスチャ要件:
- 正方形(1024x1024 以上)の **アルベド(ベースカラー)テクスチャ**。
- 対象の素材感・色・模様を表現する。光沢のハイライトや影は焼き込みすぎない(フラットなアルベド寄り)。
- ${uvMode === "smart"
    ? "Smart UV 展開で全面に貼るため、**シームレス/タイル状**に近い質感パターンが望ましい。"
    : uvMode === "view"
    ? "正面ビューから投影するため、対象を**正面から見た見た目**を画面いっぱいに描く。"
    : "球状投影で貼るため、対象表面の色・模様を素直に描く。"}
- 文字・ロゴ・枠・余計な装飾は入れない。
- 背景は対象の素材で埋める(白フチを作らない)。

注意: 有料画像APIは使わない。必ず image_gen ツールで生成し \`${cwd}/texture.png\` に保存する。`;

const APPLY_STEP = (cwd: string, engineDir: string, blender: string, uvMode: string) => `# 手順3: テクスチャをメッシュに貼って書き出す(Blender)

次のコマンドで、生成したテクスチャをメッシュに適用し、テクスチャ付き GLB と FBX を書き出す:

\`\`\`bash
"${blender}" --background --python "${engineDir}/apply_texture.py" -- \\
  --mesh "${cwd}/mesh.obj" \\
  --texture "${cwd}/texture.png" \\
  --out "${cwd}/model.glb" \\
  --fbx "${cwd}/model.fbx" \\
  --uv ${uvMode}
\`\`\`

- \`${cwd}/model.glb\`(ブラウザプレビュー用・テクスチャ埋め込み)と \`${cwd}/model.fbx\` が作られる。
- Blender が見つからない/エラーの場合は、\`--fbx\` を外して GLB だけ書き出す。それも無理なら \`mesh.obj\` をそのまま \`model.glb\` に変換(\`--texture\` なしで apply_texture.py を実行)してでも \`model.glb\` を必ず用意する。`;

const MANIFEST_STEP = (mode: string, cwd: string) => `# 手順4: 完了処理(必須)

\`${cwd}/manifest.json\` を書き出して終了する。形式:

\`\`\`json
{
  "mode": "${mode}",
  "model": "model.glb",
  "fbx": "model.fbx",
  "mesh": "mesh.obj",
  "texture": "texture.png",
  "conceptImage": "input_0.png",
  "notes": "うまくいった点・フォールバックした点を簡潔に"
}
\`\`\`

実際に生成できたファイルだけを書く(無いものはキー自体を省く)。\`model.glb\` は必ず存在させること。`;

export type ImageTo3DParams = {
  cwd: string;
  engineDir: string;
  blender: string;
  imagePaths: string[]; // cwd 内の入力画像(正面が先頭)
  subjectDesc: string; // テクスチャ生成のための対象説明(任意)
  uvMode: "smart" | "sphere" | "view";
  mcResolution: number;
};

export function buildImageTo3DPrompt(p: ImageTo3DParams): string {
  const multi = p.imagePaths.length > 1;
  const subject =
    p.subjectDesc.trim() ||
    `cwd 内の入力画像(${p.imagePaths.map((x) => x.split("/").pop()).join(", ")})に写っている対象。入力画像をよく観察して、その色・素材・模様に忠実なテクスチャにする。`;
  return `${JOB_PREAMBLE}
# あなたへの作業指示 — 画像から3Dモデル生成${multi ? "(複数視点)" : ""}

${multi
    ? `入力画像が複数あります(正面・横・後ろなど)。先頭が正面です。これらを参考に、対象の立体形状を1つの3Dモデルとして作ってください。`
    : `1枚の入力画像から、対象の3Dモデルを作ってください。`}

${COMMON_RULES(p.engineDir, p.blender, p.cwd)}

${GEOMETRY_STEP(p.cwd, p.engineDir, p.imagePaths, p.mcResolution)}

${TEXTURE_STEP(p.cwd, subject, p.uvMode)}

${APPLY_STEP(p.cwd, p.engineDir, p.blender, p.uvMode)}

${MANIFEST_STEP("image-to-3d", p.cwd)}
`;
}

export type MultiviewTo3DParams = {
  cwd: string;
  engineDir: string;
  blender: string;
  views: { name: string; path: string }[]; // front/right/back/left/top/bottom
  frontPath: string; // 形状生成に使う正面画像
  frontAxis: string; // +z 既定
  mcResolution: number;
};

export function buildMultiviewTo3DPrompt(p: MultiviewTo3DParams): string {
  const viewArgs = p.views.map((v) => `--view ${v.name}="${v.path}"`).join(" ");
  const viewList = p.views.map((v) => `${v.name}: ${v.path.split("/").pop()}`).join(" / ");
  return `${JOB_PREAMBLE}
# あなたへの作業指示 — 複数視点の写真から3Dモデル生成(本格)

複数の写真(${viewList})から、対象の3Dモデルを作ります。
形状は正面写真から生成し、見た目(テクスチャ)は**全方向の実写真をメッシュに投影**して再現します。
この方式ではテクスチャを画像生成する必要はありません(実写真を使うため)。

${COMMON_RULES(p.engineDir, p.blender, p.cwd)}

${GEOMETRY_STEP(p.cwd, p.engineDir, [p.frontPath], p.mcResolution)}

# 手順2: 複数視点の写真をメッシュに投影する(頂点カラー)

次のコマンドで、各方向の写真をメッシュに投影し、頂点カラー付き GLB を作る:

\`\`\`bash
bash "${p.engineDir}/run_multiview.sh" \\
  --mesh "${p.cwd}/mesh.obj" \\
  --out "${p.cwd}/model.glb" \\
  ${viewArgs} \\
  --front-axis ${p.frontAxis}
\`\`\`

- 成功すると \`${p.cwd}/model.glb\`(実写真の見た目を全方向に貼ったモデル)が作られる。
- 各ビューの可視頂点数がログに出る。front の可視頂点が極端に少ない場合は \`--front-axis -z\` や \`+x\`/\`-x\` を試して向きを補正する。

# 手順3: FBX も書き出す(任意・Blender)

\`\`\`bash
"${p.blender}" --background --python "${p.engineDir}/apply_texture.py" -- \\
  --mesh "${p.cwd}/model.glb" --out "${p.cwd}/model_fbx_tmp.glb" --fbx "${p.cwd}/model.fbx"
\`\`\`

- Blender がクラッシュ/失敗しても問題ない。その場合 FBX は省略してよい(\`model.glb\` があれば成功)。

${MANIFEST_STEP("multiview-to-3d", p.cwd)}
`;
}

export type TextTo3DParams = {
  cwd: string;
  engineDir: string;
  blender: string;
  prompt: string; // ユーザーが指定した作りたいオブジェクト
  uvMode: "smart" | "sphere" | "view";
  mcResolution: number;
};

export function buildTextTo3DPrompt(p: TextTo3DParams): string {
  const conceptPath = `${p.cwd}/input_0.png`;
  return `${JOB_PREAMBLE}
# あなたへの作業指示 — テキストから3Dモデル生成

ユーザーが作りたいもの: 「${p.prompt}」

これを3Dモデル化します。まず手順0でコンセプト画像を作り、それを形状生成に渡します。

${COMMON_RULES(p.engineDir, p.blender, p.cwd)}

# 手順0: コンセプト画像を生成する(あなたの image_gen ツールで)

\`${conceptPath}\` を **あなた自身の画像生成ツール** で作成する。

- 対象「${p.prompt}」を **正面から見た1体**。全体が画面に収まる。
- 背景は **完全な単色**(グレー \`#808080\` 推奨)。影・地面・テキスト・複数体は描かない。
- 形状生成(TripoSR)が立体を推定しやすいよう、対象の輪郭がはっきり分かる構図にする。
- 有料画像APIは使わない。image_gen ツールで生成し \`${conceptPath}\` に保存する。

${GEOMETRY_STEP(p.cwd, p.engineDir, [conceptPath], p.mcResolution)}

${TEXTURE_STEP(p.cwd, `「${p.prompt}」。手順0で作った ${conceptPath} の色・素材に合わせる。`, p.uvMode)}

${APPLY_STEP(p.cwd, p.engineDir, p.blender, p.uvMode)}

${MANIFEST_STEP("text-to-3d", p.cwd)}
`;
}
