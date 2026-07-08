import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { BLENDER_PATH, engineDir } from "@/lib/paths";

export type BlenderApplyOptions = {
  cwd: string;
  mesh: string; // 例: mesh.obj
  texture?: string; // 例: texture.png (無ければ頂点カラー)
  out: string; // 例: model.glb
  fbx?: string; // 例: model.fbx
  uv?: "smart" | "sphere" | "view";
};

/**
 * Node(サンドボックス外)から直接 Blender を実行してテクスチャ適用 + GLB/FBX 書き出し。
 * Codex 側のサンドボックスで Blender がブロックされた場合のフォールバックに使う。
 */
export function runBlenderApply(opts: BlenderApplyOptions): Promise<{ ok: boolean; log: string }> {
  return new Promise((resolve) => {
    if (!fs.existsSync(BLENDER_PATH)) {
      resolve({ ok: false, log: `Blender が見つかりません: ${BLENDER_PATH}` });
      return;
    }
    const script = path.join(engineDir(), "apply_texture.py");
    const args = [
      "--background",
      "--python", script,
      "--",
      "--mesh", path.resolve(opts.cwd, opts.mesh),
      "--out", path.resolve(opts.cwd, opts.out),
      "--uv", opts.uv || "smart",
    ];
    if (opts.texture && fs.existsSync(path.resolve(opts.cwd, opts.texture))) {
      args.push("--texture", path.resolve(opts.cwd, opts.texture));
    }
    if (opts.fbx) {
      args.push("--fbx", path.resolve(opts.cwd, opts.fbx));
    }

    const p = spawn(BLENDER_PATH, args, {
      cwd: opts.cwd,
      env: { ...process.env, TMPDIR: os.tmpdir() },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let log = "";
    p.stdout.on("data", (b) => (log += b.toString()));
    p.stderr.on("data", (b) => (log += b.toString()));
    p.on("error", (e) => resolve({ ok: false, log: log + "\n" + String(e) }));
    p.on("exit", (code) => {
      const ok = code === 0 && fs.existsSync(path.resolve(opts.cwd, opts.out));
      resolve({ ok, log: log.slice(-2000) });
    });
  });
}

export type MultiviewProjectOptions = {
  cwd: string;
  mesh: string; // mesh.obj
  out: string; // model.glb
  views: { name: string; path: string }[];
  frontAxis?: string;
};

/**
 * Node から複数視点投影(run_multiview.sh)を実行するフォールバック。
 * Codex 側で model.glb が出来なかった場合に使う。
 */
export function runMultiviewProject(opts: MultiviewProjectOptions): Promise<{ ok: boolean; log: string }> {
  return new Promise((resolve) => {
    const script = path.join(engineDir(), "run_multiview.sh");
    if (!fs.existsSync(script)) {
      resolve({ ok: false, log: `run_multiview.sh が見つかりません: ${script}` });
      return;
    }
    const args = [
      script,
      "--mesh", path.resolve(opts.cwd, opts.mesh),
      "--out", path.resolve(opts.cwd, opts.out),
      "--front-axis", opts.frontAxis || "+z",
    ];
    for (const v of opts.views) {
      args.push("--view", `${v.name}=${v.path}`);
    }
    const p = spawn("bash", args, {
      cwd: opts.cwd,
      env: { ...process.env },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let log = "";
    p.stdout.on("data", (b) => (log += b.toString()));
    p.stderr.on("data", (b) => (log += b.toString()));
    p.on("error", (e) => resolve({ ok: false, log: log + "\n" + String(e) }));
    p.on("exit", (code) => {
      const ok = code === 0 && fs.existsSync(path.resolve(opts.cwd, opts.out));
      resolve({ ok, log: log.slice(-2000) });
    });
  });
}
