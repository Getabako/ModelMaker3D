import fs from "node:fs";
import path from "node:path";
import { NextRequest } from "next/server";
import { resolveSaveRoot, jobDirUnder, ensureDir, newId, engineDir, BLENDER_PATH } from "@/lib/paths";
import { buildMultiviewTo3DPrompt } from "@/lib/prompt3d";
import { runJobStream } from "@/lib/runJob";
import { runMultiviewProject, runBlenderApply } from "@/lib/blender";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const VALID = ["front", "right", "back", "left", "top", "bottom"];

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const images = form.getAll("images").filter((x): x is File => x instanceof File);
  let labels: string[] = [];
  try {
    labels = JSON.parse(String(form.get("viewLabels") ?? "[]"));
  } catch {}
  const frontAxis = String(form.get("frontAxis") ?? "+z");
  const mcResolution = parseInt(String(form.get("mcResolution") ?? "256"), 10) || 256;
  const saveRoot = resolveSaveRoot(String(form.get("saveRoot") ?? ""));

  if (images.length < 2) return new Response("複数視点には2枚以上の画像が必要です", { status: 400 });

  const id = newId("mv3d");
  const cwd = jobDirUnder(saveRoot, id);
  ensureDir(cwd);

  // 画像を保存し、ビュー名を割り当てる(指定が無ければ順に front/right/back/left/top/bottom)。
  const views: { name: string; path: string }[] = [];
  for (let i = 0; i < images.length; i++) {
    const buf = Buffer.from(await images[i].arrayBuffer());
    let name = (labels[i] || VALID[i] || `view${i}`).toLowerCase();
    if (!VALID.includes(name)) name = VALID[i] || "front";
    const fname = `${name}.png`;
    fs.writeFileSync(path.join(cwd, fname), buf);
    views.push({ name, path: path.join(cwd, fname) });
  }
  // front を決定(無ければ最初の画像を front 扱い)
  const front = views.find((v) => v.name === "front") ?? views[0];
  const frontPath = front.path;

  const prompt = buildMultiviewTo3DPrompt({
    cwd,
    engineDir: engineDir(),
    blender: BLENDER_PATH,
    views,
    frontPath,
    frontAxis,
    mcResolution,
  });
  fs.writeFileSync(path.join(cwd, "prompt.txt"), prompt, "utf8");

  return runJobStream({
    cwd,
    prompt,
    serviceName: "modelmaker3d-multiview",
    req,
    initData: { id, mode: "multiview-to-3d", savedTo: cwd, views: views.map((v) => v.name) },
    finalize: async () => {
      const glb = path.join(cwd, "model.glb");
      // フォールバック: Codex 側で model.glb が無ければ Node から投影を実行
      if (!fs.existsSync(glb) && fs.existsSync(path.join(cwd, "mesh.obj"))) {
        await runMultiviewProject({ cwd, mesh: "mesh.obj", out: "model.glb", views, frontAxis });
      }
      // FBX が無ければ Node から Blender で変換(失敗しても無視)
      if (fs.existsSync(glb) && !fs.existsSync(path.join(cwd, "model.fbx"))) {
        await runBlenderApply({ cwd, mesh: "model.glb", out: "model_fbxtmp.glb", fbx: "model.fbx" }).catch(() => {});
      }
      if (!fs.existsSync(glb)) throw new Error("model.glb が生成されませんでした");
      const fileUrl = (f: string) =>
        `/api/jobs/file?dir=${encodeURIComponent(cwd)}&file=${encodeURIComponent(f)}`;
      const has = (f: string) => fs.existsSync(path.join(cwd, f));
      return {
        id,
        mode: "multiview-to-3d",
        savedTo: cwd,
        modelUrl: fileUrl("model.glb"),
        fbxUrl: has("model.fbx") ? fileUrl("model.fbx") : null,
        objUrl: has("mesh.obj") ? fileUrl("mesh.obj") : null,
      };
    },
  });
}
