import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import type { NextRequest } from "next/server";
import { getCodex } from "@/lib/codex/client";

type NotifParams = {
  thread?: { id?: string };
  status?: { type?: string };
  plan?: Array<{ step: string; status: string }>;
  item?: {
    type?: string;
    command?: string[] | string;
    changes?: Array<{ path?: string }>;
    text?: string;
    exitCode?: number;
  };
  delta?: string;
  chunk?: string;
  output?: string;
};
type Notif = { method: string; params?: NotifParams };

export type RunJobOptions = {
  cwd: string;
  prompt: string;
  serviceName: string;
  req: NextRequest;
  initData: Record<string, unknown>;
  finalize: () => Record<string, unknown> | Promise<Record<string, unknown>>;
};

/** Codex に 1 ターン投げて SSE で進捗をストリームする共通処理。 */
export function runJobStream(opts: RunJobOptions): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      let closed = false;
      const send = (event: string, data: unknown) => {
        if (closed) return;
        try {
          controller.enqueue(
            encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
          );
        } catch {}
      };
      const close = () => {
        if (closed) return;
        closed = true;
        try { controller.close(); } catch {}
      };

      send("init", opts.initData);

      const srv = await getCodex();
      let threadId: string | null = null;
      let turnId: string | null = null;
      let turnDone = false;
      const startedAt = Date.now();

      const heartbeat = setInterval(() => {
        send("heartbeat", { elapsedSec: Math.floor((Date.now() - startedAt) / 1000) });
      }, 3000);

      const onStderr = (text: string) => {
        const t = text.trim();
        if (t) send("stderr", { text: t.slice(0, 500) });
      };
      srv.on("stderr", onStderr);

      const onNotif = (notif: Notif) => {
        const { method, params } = notif;
        if (!params) return;
        switch (method) {
          case "thread/started":
            threadId = params.thread?.id ?? null;
            send("step", { kind: "thread", text: `🧵 ${threadId}` });
            return;
          case "thread/status/changed":
            if (params.status?.type) {
              send("step", {
                kind: params.status.type === "systemError" ? "error" : "status",
                text: `status: ${params.status.type}`,
              });
              if (params.status.type === "systemError") turnDone = true;
            }
            return;
          case "turn/plan/updated": {
            const plan = params.plan ?? [];
            const summary = plan
              .map((p) =>
                `${p.status === "completed" ? "✓" : p.status === "inProgress" ? "▸" : "·"} ${p.step}`,
              )
              .join(" / ");
            if (summary) send("step", { kind: "plan", text: `📋 ${summary}` });
            return;
          }
          case "item/started": {
            const item = params.item;
            if (!item) return;
            if (item.type === "agentMessage") return;
            if (item.type === "reasoning") {
              send("step", { kind: "reasoning", text: "🧠 思考中…" });
            } else if (item.type === "commandExecution") {
              const cmd = Array.isArray(item.command)
                ? item.command.join(" ")
                : String(item.command ?? "");
              send("step", { kind: "command", text: `$ ${cmd.slice(0, 200)}` });
            } else if (item.type === "fileChange") {
              const files = (item.changes || []).map((c) => c.path).join(", ");
              send("step", { kind: "file", text: `📄 ${files}` });
            } else {
              send("step", { kind: "info", text: `▸ ${item.type}` });
            }
            return;
          }
          case "item/agentMessage/delta":
            send("delta", { text: params.delta ?? "" });
            return;
          case "item/reasoning/summaryTextDelta":
            send("reasoning_delta", { text: params.delta ?? "" });
            return;
          case "item/commandExecution/outputDelta":
            send("cmd_output", {
              text: String(params.chunk ?? params.output ?? "").slice(0, 200),
            });
            return;
          case "item/completed": {
            const item = params.item;
            if (!item) return;
            if (item.type === "agentMessage" && item.text) {
              send("agent", { text: item.text });
            } else if (item.type === "commandExecution") {
              send("step", {
                kind: item.exitCode === 0 ? "command-ok" : "command-err",
                text: `↳ exit ${item.exitCode}`,
              });
            } else if (item.type === "fileChange") {
              const files = (item.changes || []).map((c) => c.path).join(", ");
              send("step", { kind: "file-ok", text: `✓ ${files}` });
            }
            return;
          }
          case "turn/completed":
            turnDone = true;
            return;
        }
      };
      srv.on("notification", onNotif);

      const cleanup = () => {
        clearInterval(heartbeat);
        srv.off("notification", onNotif);
        srv.off("stderr", onStderr);
      };

      opts.req.signal.addEventListener("abort", () => {
        if (threadId && turnId) {
          srv.send("turn/interrupt", { threadId, turnId }).catch(() => {});
        }
        cleanup();
        close();
      });

      try {
        const model = process.env.MODELMAKER_MODEL || "gpt-5.5";
        const effort = process.env.MODELMAKER_EFFORT || "medium";
        send("step", { kind: "info", text: `thread/start (model=${model}, effort=${effort})` });

        // 形状生成(TripoSR)やテクスチャ生成はモデルキャッシュ($HOME/.cache 等)へ書き込む。
        // cwd に加えてキャッシュ/ホームの一部を書き込み可能にする。
        const home = os.homedir();
        const writableRoots = [
          opts.cwd,
          path.join(home, ".cache"),
          path.join(home, ".u2net"),
          path.join(home, ".config"),
          // Blender が設定/一時ファイルを書き込む場所(テクスチャ適用ステップ用)
          path.join(home, "Library", "Application Support", "Blender"),
          path.join(home, "Library", "Caches"),
          path.join(home, ".codex", "generated_images"),
          os.tmpdir(),
        ];

        const started = (await srv.send("thread/start", {
          cwd: opts.cwd,
          model,
          effort,
          sandbox: "workspace-write",
          approvalPolicy: "never",
          serviceName: opts.serviceName,
        })) as { thread: { id: string } };
        threadId = started.thread.id;

        const turn = (await srv.send("turn/start", {
          threadId,
          input: [{ type: "text", text: opts.prompt }],
          cwd: opts.cwd,
          model,
          effort,
          sandboxPolicy: {
            type: "workspaceWrite",
            writableRoots,
            networkAccess: true,
          },
          approvalPolicy: "never",
        })) as { turn: { id: string } };
        turnId = turn.turn.id;

        await new Promise<void>((resolve) => {
          const tick = setInterval(() => {
            if (turnDone) {
              clearInterval(tick);
              resolve();
            }
          }, 200);
          opts.req.signal.addEventListener("abort", () => {
            clearInterval(tick);
            resolve();
          });
        });

        const result = await opts.finalize();
        send("done", result);
      } catch (err) {
        send("error", { message: (err as Error).message });
      } finally {
        cleanup();
        close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}

/** multipart/form-data から入力画像を取り出して cwd/input_0.png, input_1.png ... に保存。 */
export async function saveInputImages(files: File[], cwd: string): Promise<string[]> {
  const saved: string[] = [];
  for (let i = 0; i < files.length; i++) {
    const buf = Buffer.from(await files[i].arrayBuffer());
    const name = `input_${i}.png`;
    fs.writeFileSync(path.join(cwd, name), buf);
    saved.push(path.join(cwd, name));
  }
  return saved;
}
