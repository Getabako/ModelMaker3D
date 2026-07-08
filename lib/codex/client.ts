import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import readline from "node:readline";
import type { ChildProcessWithoutNullStreams } from "node:child_process";

type JsonRpcResponse = {
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
};

type JsonRpcNotification = {
  method: string;
  params?: unknown;
};

/** Single local app-server instance using the user's existing ~/.codex. */
export class CodexAppServer extends EventEmitter {
  private proc: ChildProcessWithoutNullStreams;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  >();
  private initialized = false;
  private initializingPromise: Promise<void> | null = null;

  constructor() {
    super();
    this.proc = spawn("codex", ["app-server"], {
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const rl = readline.createInterface({ input: this.proc.stdout });
    rl.on("line", (line) => this.handleLine(line));

    this.proc.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      console.error("[codex]", text.trimEnd());
      this.emit("stderr", text);
    });

    this.proc.on("exit", (code, signal) => {
      console.log(`[codex] exited code=${code} signal=${signal}`);
      this.emit("exit", { code, signal });
      for (const { reject } of this.pending.values()) {
        reject(new Error(`app-server exited (code=${code})`));
      }
      this.pending.clear();
    });
  }

  private handleLine(line: string) {
    const trimmed = line.trim();
    if (!trimmed) return;
    let msg: JsonRpcResponse | JsonRpcNotification;
    try {
      msg = JSON.parse(trimmed);
    } catch {
      console.error("[codex] bad json:", trimmed.slice(0, 200));
      return;
    }

    if ("id" in msg && msg.id !== undefined && msg.id !== null) {
      const resp = msg as JsonRpcResponse;
      const pending = this.pending.get(resp.id);
      if (pending) {
        this.pending.delete(resp.id);
        if (resp.error) {
          pending.reject(new Error(`${resp.error.code}: ${resp.error.message}`));
        } else {
          pending.resolve(resp.result);
        }
      }
      return;
    }

    const notif = msg as JsonRpcNotification;
    this.emit("notification", notif);
    this.emit(`notify:${notif.method}`, notif.params);
  }

  private write(obj: object) {
    this.proc.stdin.write(JSON.stringify(obj) + "\n");
  }

  send<T = unknown>(method: string, params?: unknown): Promise<T> {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, {
        resolve: (v) => resolve(v as T),
        reject,
      });
      this.write({ method, id, params });
    });
  }

  notify(method: string, params?: unknown) {
    this.write({ method, params });
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    if (this.initializingPromise) return this.initializingPromise;

    this.initializingPromise = (async () => {
      await this.send("initialize", {
        clientInfo: {
          name: "codex_cli",
          title: "AnimeMaker (codex-cli compatible)",
          version: "0.1.0",
        },
        capabilities: { experimentalApi: true },
      });
      this.notify("initialized", {});
      this.initialized = true;
    })();

    return this.initializingPromise;
  }

  kill() {
    try {
      this.proc.kill("SIGTERM");
    } catch {}
  }

  get alive() {
    return this.proc.exitCode === null;
  }
}

declare global {
  // eslint-disable-next-line no-var
  var __codexServer: CodexAppServer | undefined;
}

export async function getCodex(): Promise<CodexAppServer> {
  let s = globalThis.__codexServer;
  if (s && !s.alive) {
    globalThis.__codexServer = undefined;
    s = undefined;
  }
  if (!s) {
    s = new CodexAppServer();
    globalThis.__codexServer = s;
  }
  await s.initialize();
  return s;
}
