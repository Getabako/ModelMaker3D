import fs from "node:fs";
import path from "node:path";
import { NextRequest } from "next/server";
import { resolveSaveRoot, jobDirUnder, ensureDir, newId, engineDir, BLENDER_PATH } from "@/lib/paths";
import { buildTextTo3DPrompt } from "@/lib/prompt3d";
import { runJobStream } from "@/lib/runJob";
import { runBlenderApply } from "@/lib/blender";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const textPrompt = String(form.get("prompt") ?? "").trim();
  const uvMode = (String(form.get("uvMode") ?? "smart") as "smart" | "sphere" | "view");
  const mcResolution = parseInt(String(form.get("mcResolution") ?? "256"), 10) || 256;
  const saveRoot = resolveSaveRoot(String(form.get("saveRoot") ?? ""));

  if (!textPrompt) return new Response("prompt is required", { status: 400 });

  const id = newId("txt3d");
  const cwd = jobDirUnder(saveRoot, id);
  ensureDir(cwd);

  const prompt = buildTextTo3DPrompt({
    cwd,
    engineDir: engineDir(),
    blender: BLENDER_PATH,
    prompt: textPrompt,
    uvMode,
    mcResolution,
  });
  fs.writeFileSync(path.join(cwd, "prompt.txt"), prompt, "utf8");

  return runJobStream({
    cwd,
    prompt,
    serviceName: "modelmaker3d-text",
    req,
    initData: { id, mode: "text-to-3d", savedTo: cwd },
    finalize: async () => {
      const glb = path.join(cwd, "model.glb");
      // Codex 側で model.glb が出来ていなければ Node から Blender を実行して仕上げる(フォールバック)。
      if (!fs.existsSync(glb) && fs.existsSync(path.join(cwd, "mesh.obj"))) {
        await runBlenderApply({
          cwd, mesh: "mesh.obj",
          texture: fs.existsSync(path.join(cwd, "texture.png")) ? "texture.png" : undefined,
          out: "model.glb", fbx: "model.fbx", uv: uvMode,
        });
      }
      if (!fs.existsSync(glb)) throw new Error("model.glb が生成されませんでした");
      const fileUrl = (f: string) =>
        `/api/jobs/file?dir=${encodeURIComponent(cwd)}&file=${encodeURIComponent(f)}`;
      const has = (f: string) => fs.existsSync(path.join(cwd, f));
      return {
        id,
        mode: "text-to-3d",
        savedTo: cwd,
        modelUrl: fileUrl("model.glb"),
        fbxUrl: has("model.fbx") ? fileUrl("model.fbx") : null,
        objUrl: has("mesh.obj") ? fileUrl("mesh.obj") : null,
        textureUrl: has("texture.png") ? fileUrl("texture.png") : null,
        conceptUrl: has("input_0.png") ? fileUrl("input_0.png") : null,
      };
    },
  });
}
