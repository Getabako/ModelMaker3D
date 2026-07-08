import fs from "node:fs";
import path from "node:path";
import { NextRequest } from "next/server";
import { resolveSaveRoot, jobDirUnder, ensureDir, newId, engineDir, BLENDER_PATH } from "@/lib/paths";
import { buildImageTo3DPrompt } from "@/lib/prompt3d";
import { runJobStream, saveInputImages } from "@/lib/runJob";
import { runBlenderApply } from "@/lib/blender";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const images = form.getAll("images").filter((x): x is File => x instanceof File);
  const subjectDesc = String(form.get("subjectDesc") ?? "").trim();
  const uvMode = (String(form.get("uvMode") ?? "smart") as "smart" | "sphere" | "view");
  const mcResolution = parseInt(String(form.get("mcResolution") ?? "256"), 10) || 256;
  const saveRoot = resolveSaveRoot(String(form.get("saveRoot") ?? ""));

  if (images.length === 0) return new Response("images is required", { status: 400 });

  const id = newId("img3d");
  const cwd = jobDirUnder(saveRoot, id);
  ensureDir(cwd);
  const imagePaths = await saveInputImages(images, cwd);

  const prompt = buildImageTo3DPrompt({
    cwd,
    engineDir: engineDir(),
    blender: BLENDER_PATH,
    imagePaths,
    subjectDesc,
    uvMode,
    mcResolution,
  });
  fs.writeFileSync(path.join(cwd, "prompt.txt"), prompt, "utf8");

  return runJobStream({
    cwd,
    prompt,
    serviceName: "modelmaker3d-image",
    req,
    initData: { id, mode: "image-to-3d", savedTo: cwd, inputs: imagePaths.length },
    finalize: async () => {
      const glb = path.join(cwd, "model.glb");
      // Codex 側で model.glb が出来ていなければ、Node から直接 Blender を実行して仕上げる
      // (Codex サンドボックスで Blender がブロックされた場合のフォールバック)。
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
        mode: "image-to-3d",
        savedTo: cwd,
        modelUrl: fileUrl("model.glb"),
        fbxUrl: has("model.fbx") ? fileUrl("model.fbx") : null,
        objUrl: has("mesh.obj") ? fileUrl("mesh.obj") : null,
        textureUrl: has("texture.png") ? fileUrl("texture.png") : null,
      };
    },
  });
}
