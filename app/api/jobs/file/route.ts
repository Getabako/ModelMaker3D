import fs from "node:fs";
import path from "node:path";
import { NextRequest } from "next/server";

export const runtime = "nodejs";

// ジョブ成果物 (任意の保存先ディレクトリの中) を配信する。
// セキュリティ: file は拡張子と文字種を制限し、dir 配下にとどまることを保証。
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const dir = url.searchParams.get("dir") || "";
  const file = url.searchParams.get("file") || "";
  if (!dir || !file) return new Response("bad query", { status: 400 });
  if (!path.isAbsolute(dir)) return new Response("dir must be absolute", { status: 400 });
  if (!/^[\w.+\-]+\.(png|jpg|jpeg|json|txt|glb|gltf|obj|mtl|fbx|bin|ply|zip)$/i.test(file)) {
    return new Response("bad file name", { status: 400 });
  }
  const full = path.resolve(dir, file);
  if (!full.startsWith(path.resolve(dir) + path.sep) && full !== path.resolve(dir, file)) {
    return new Response("forbidden", { status: 403 });
  }
  if (!fs.existsSync(full)) return new Response("not found", { status: 404 });

  const buf = fs.readFileSync(full);
  const ext = file.toLowerCase().split(".").pop() || "";
  const type =
    ext === "png" ? "image/png" :
    ext === "jpg" || ext === "jpeg" ? "image/jpeg" :
    ext === "json" ? "application/json; charset=utf-8" :
    ext === "glb" ? "model/gltf-binary" :
    ext === "gltf" ? "model/gltf+json" :
    ext === "obj" ? "text/plain; charset=utf-8" :
    ext === "fbx" ? "application/octet-stream" :
    ext === "ply" ? "application/octet-stream" :
    ext === "bin" ? "application/octet-stream" :
    ext === "zip" ? "application/zip" :
    "text/plain; charset=utf-8";

  return new Response(buf as unknown as BodyInit, {
    headers: {
      "Content-Type": type,
      "Cache-Control": "no-cache",
      "Content-Disposition": `inline; filename="${file}"`,
    },
  });
}
