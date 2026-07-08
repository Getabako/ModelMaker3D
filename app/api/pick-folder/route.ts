import { spawn } from "node:child_process";
import os from "node:os";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// OS ネイティブのフォルダ選択ダイアログを開いて絶対パスを返す。
// このアプリは localhost で動くので、サーバー = ユーザーの PC。
export async function POST() {
  try {
    const platform = process.platform;
    let cmd: string;
    let args: string[];

    if (platform === "darwin") {
      cmd = "osascript";
      args = [
        "-e",
        'POSIX path of (choose folder with prompt "AnimeMaker - ホゾンサキ ヲ センタク シテクダサイ")',
      ];
    } else if (platform === "win32") {
      const ps = `
Add-Type -AssemblyName System.Windows.Forms
$dlg = New-Object System.Windows.Forms.FolderBrowserDialog
$dlg.Description = "AnimeMaker - 保存先フォルダを選択してください"
$dlg.ShowNewFolderButton = $true
if ($dlg.ShowDialog() -eq "OK") { Write-Output $dlg.SelectedPath }
`.trim();
      cmd = "powershell";
      args = ["-NoProfile", "-NonInteractive", "-Command", ps];
    } else {
      // Linux: zenity があれば利用
      cmd = "zenity";
      args = ["--file-selection", "--directory", "--title=AnimeMaker"];
    }

    const path = await runAndCapture(cmd, args);
    if (!path) return Response.json({ cancelled: true });
    return Response.json({ path });
  } catch (e) {
    return new Response((e as Error).message, { status: 500 });
  }
}

function runAndCapture(cmd: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let out = "";
    let err = "";
    p.stdout.on("data", (b) => (out += b.toString()));
    p.stderr.on("data", (b) => (err += b.toString()));
    p.on("error", (e) => reject(e));
    p.on("exit", (code) => {
      // macOS の osascript: キャンセル時は exit code 1 + stderr に "User canceled."
      if (/User canceled/i.test(err)) return resolve("");
      if (code !== 0 && !out.trim()) return resolve("");
      const result = out.trim().replace(/\/$/, "");
      // macOS は ~ なしの絶対パスで返る。Windows / Linux も絶対パス想定。
      void os; // satisfy lint
      resolve(result);
    });
  });
}
