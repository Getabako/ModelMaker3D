#!/usr/bin/env node
/**
 * ModelMaker3D — local web UI for codex app-server.
 * 画像/複数視点/テキスト から 3Dモデル(GLB/FBX)を生成する。
 * 形状は TripoSR をローカル実行、テクスチャは Codex 画像生成。有料APIは使わない。
 */
const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const net = require("node:net");

const PKG_ROOT = path.resolve(__dirname, "..");
const STANDALONE = path.join(PKG_ROOT, ".next", "standalone", "server.js");

function check(cmd) {
  return new Promise((resolve) => {
    const p = spawn(cmd, ["--version"], { stdio: "ignore" });
    p.on("error", () => resolve(false));
    p.on("exit", (code) => resolve(code === 0));
  });
}

function pickPort(start) {
  return new Promise((resolve) => {
    const try1 = (p) => {
      const srv = net.createServer();
      srv.once("error", () => try1(p + 1));
      srv.listen(p, "127.0.0.1", () => {
        const port = srv.address().port;
        srv.close(() => resolve(port));
      });
    };
    try1(start);
  });
}

(async () => {
  if (!(await check("codex"))) {
    console.error(
      "✗ `codex` CLI が見つかりません。先に Codex CLI をインストールしてください:\n" +
        "  brew install codex   # macOS\n" +
        "  または https://developers.openai.com/codex を参照",
    );
    process.exit(1);
  }

  // TripoSR 実行環境(conda env)が無ければ警告(致命的ではない)。
  const condaEnv = "/opt/homebrew/Caskroom/miniconda/base/envs/triposr311";
  if (!fs.existsSync(condaEnv)) {
    console.warn(
      "⚠ TripoSR 環境 (conda env: triposr311) が見つかりません。\n" +
        "  形状生成を使う前に `npm run setup-engine` を実行してください。",
    );
  }

  if (!fs.existsSync(STANDALONE)) {
    console.error(
      `✗ ビルド成果物が見つかりません: ${STANDALONE}\n` +
        "  リポジトリ直下で `npm run build` を実行してください。",
    );
    process.exit(1);
  }

  const port = await pickPort(Number(process.env.PORT) || 4573);
  const url = `http://localhost:${port}`;

  const standaloneDir = path.dirname(STANDALONE);
  const staticSrc = path.join(PKG_ROOT, ".next", "static");
  const staticDst = path.join(standaloneDir, ".next", "static");
  if (fs.existsSync(staticSrc)) {
    fs.rmSync(staticDst, { recursive: true, force: true });
    fs.mkdirSync(path.dirname(staticDst), { recursive: true });
    fs.cpSync(staticSrc, staticDst, { recursive: true });
  }
  const publicSrc = path.join(PKG_ROOT, "public");
  const publicDst = path.join(standaloneDir, "public");
  if (fs.existsSync(publicSrc)) {
    fs.rmSync(publicDst, { recursive: true, force: true });
    fs.cpSync(publicSrc, publicDst, { recursive: true });
  }

  console.log("");
  console.log("=".repeat(56));
  console.log(`  ▶ ModelMaker3D 起動完了`);
  console.log(`  ▶ ブラウザで開く:  ${url}`);
  console.log(`  ▶ 終了するには:    Ctrl+C`);
  console.log("=".repeat(56));
  console.log("");

  // engine ディレクトリを cwd から解決できるよう、standalone 実行時の cwd を
  // PKG_ROOT にして engine/ を見つけられるようにする。
  const child = spawn(process.execPath, [STANDALONE], {
    cwd: PKG_ROOT,
    env: { ...process.env, PORT: String(port), HOSTNAME: "127.0.0.1" },
    stdio: "inherit",
  });

  const shutdown = () => {
    try { child.kill("SIGTERM"); } catch {}
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
  child.on("exit", (code) => process.exit(code ?? 0));
})();
