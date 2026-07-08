import { NextRequest } from "next/server";
import { DEFAULT_SAVE_ROOT, resolveSaveRoot, ensureDir } from "@/lib/paths";
import fs from "node:fs";

export const runtime = "nodejs";

// デフォルト保存先を返す。
export async function GET() {
  return Response.json({ defaultSaveRoot: DEFAULT_SAVE_ROOT });
}

// 指定パスを検証して、存在しなければ作成。
export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as { path?: string };
  try {
    const resolved = resolveSaveRoot(body.path);
    ensureDir(resolved);
    const stat = fs.statSync(resolved);
    if (!stat.isDirectory()) {
      return new Response("指定パスはディレクトリではありません", { status: 400 });
    }
    return Response.json({ ok: true, saveRoot: resolved });
  } catch (e) {
    return new Response((e as Error).message, { status: 400 });
  }
}
