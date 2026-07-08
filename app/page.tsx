"use client";

import { useEffect, useRef, useState } from "react";

type Mode = "image" | "multiview" | "text";
type LogLine = { kind: string; text: string };

type DoneResult = {
  id: string;
  mode: string;
  savedTo: string;
  modelUrl: string;
  fbxUrl?: string | null;
  objUrl?: string | null;
  textureUrl?: string | null;
  conceptUrl?: string | null;
};

const UV_OPTIONS = [
  { v: "smart", label: "おまかせ（汎用・素材向き）" },
  { v: "view", label: "正面投影（写真風）" },
  { v: "sphere", label: "球状（丸い物・有機物）" },
];

const VIEW_OPTIONS = [
  { v: "front", label: "正面" },
  { v: "right", label: "右横" },
  { v: "back", label: "後ろ" },
  { v: "left", label: "左横" },
  { v: "top", label: "上" },
  { v: "bottom", label: "下" },
];

const FRONT_AXIS_OPTIONS = [
  { v: "+z", label: "標準（+Z）" },
  { v: "-z", label: "反転（-Z）" },
  { v: "+x", label: "右向き（+X）" },
  { v: "-x", label: "左向き（-X）" },
];

export default function Home() {
  const [mode, setMode] = useState<Mode>("image");
  const [saveRoot, setSaveRoot] = useState("");
  const [defaultRoot, setDefaultRoot] = useState("");

  // 入力
  const [images, setImages] = useState<File[]>([]);
  const [viewLabels, setViewLabels] = useState<string[]>([]);
  const [frontAxis, setFrontAxis] = useState("+z");
  const [textPrompt, setTextPrompt] = useState("");
  const [subjectDesc, setSubjectDesc] = useState("");
  const [uvMode, setUvMode] = useState("smart");
  const [mcResolution, setMcResolution] = useState(256);

  // 実行
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [agentMsg, setAgentMsg] = useState("");
  const [result, setResult] = useState<DoneResult | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetch("/api/save-root")
      .then((r) => r.json())
      .then((d) => setDefaultRoot(d.defaultSaveRoot))
      .catch(() => {});
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, agentMsg]);

  function pushLog(kind: string, text: string) {
    setLogs((prev) => [...prev, { kind, text }]);
  }

  function onPickImages(files: File[]) {
    setImages(files);
    // 既定のビュー割り当て: 正面→右横→後ろ→左横→上→下
    const defaults = ["front", "right", "back", "left", "top", "bottom"];
    setViewLabels(files.map((_, i) => defaults[i] || "front"));
  }

  function setLabelAt(i: number, v: string) {
    setViewLabels((prev) => {
      const next = [...prev];
      next[i] = v;
      return next;
    });
  }

  async function pickFolder() {
    try {
      const r = await fetch("/api/pick-folder", { method: "POST" });
      const d = await r.json();
      if (d.path) setSaveRoot(d.path);
    } catch {}
  }

  function reset() {
    setLogs([]);
    setAgentMsg("");
    setResult(null);
    setElapsed(0);
  }

  async function run() {
    reset();
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const fd = new FormData();
    fd.append("saveRoot", saveRoot);
    fd.append("mcResolution", String(mcResolution));

    let endpoint = "";
    if (mode === "text") {
      if (!textPrompt.trim()) { pushLog("error", "作りたいものを入力してください"); setRunning(false); return; }
      endpoint = "/api/text-to-3d";
      fd.append("prompt", textPrompt);
      fd.append("uvMode", uvMode);
    } else if (mode === "multiview") {
      if (images.length < 2) { pushLog("error", "複数視点には2枚以上の画像が必要です"); setRunning(false); return; }
      endpoint = "/api/multiview-to-3d";
      images.forEach((f) => fd.append("images", f));
      fd.append("viewLabels", JSON.stringify(viewLabels));
      fd.append("frontAxis", frontAxis);
    } else {
      if (images.length === 0) { pushLog("error", "画像を選択してください"); setRunning(false); return; }
      endpoint = "/api/image-to-3d";
      images.forEach((f) => fd.append("images", f));
      fd.append("uvMode", uvMode);
      if (subjectDesc.trim()) fd.append("subjectDesc", subjectDesc);
    }

    try {
      const res = await fetch(endpoint, { method: "POST", body: fd, signal: ctrl.signal });
      if (!res.ok || !res.body) {
        pushLog("error", `リクエスト失敗: ${res.status} ${await res.text()}`);
        setRunning(false);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split("\n\n");
        buf = events.pop() || "";
        for (const ev of events) {
          const lines = ev.split("\n");
          const evType = lines.find((l) => l.startsWith("event: "))?.slice(7) || "";
          const dataStr = lines.find((l) => l.startsWith("data: "))?.slice(6) || "{}";
          let data: Record<string, unknown> = {};
          try { data = JSON.parse(dataStr); } catch {}
          handleEvent(evType, data);
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") pushLog("error", String((e as Error).message));
    } finally {
      setRunning(false);
    }
  }

  function handleEvent(evType: string, data: Record<string, unknown>) {
    switch (evType) {
      case "init":
        pushLog("info", `ジョブ開始: ${data.id}（保存先: ${data.savedTo}）`);
        break;
      case "heartbeat":
        setElapsed(Number(data.elapsedSec) || 0);
        break;
      case "step":
        pushLog(String(data.kind || "info"), String(data.text || ""));
        break;
      case "cmd_output":
        if (data.text) pushLog("cmd", String(data.text));
        break;
      case "delta":
        setAgentMsg((p) => p + String(data.text || ""));
        break;
      case "agent":
        setAgentMsg(String(data.text || ""));
        break;
      case "stderr":
        pushLog("cmd", String(data.text || ""));
        break;
      case "done":
        pushLog("done", "完了しました");
        setResult(data as unknown as DoneResult);
        break;
      case "error":
        pushLog("error", `エラー: ${String(data.message || "")}`);
        break;
    }
  }

  function stop() {
    abortRef.current?.abort();
    setRunning(false);
    pushLog("error", "中断しました");
  }

  return (
    <main style={{ maxWidth: 980, margin: "0 auto", padding: "32px 20px 80px", width: "100%" }}>
      <h1 style={{ fontSize: 22, marginBottom: 8 }}>ModelMaker3D</h1>
      <p className="dq-hint" style={{ marginTop: 0 }}>
        画像 ・ 複数視点 ・ テキスト から 3Dモデル（GLB / FBX）を生成します。形状はこのMacのローカルAI（TripoSR）、テクスチャはCodexの画像生成。有料APIは使いません。
      </p>

      {/* 保存先 */}
      <div className="dq-frame" style={{ marginBottom: 20 }}>
        <label className="dq-label">保存先フォルダ（絶対パス）</label>
        <div style={{ display: "flex", gap: 10 }}>
          <input
            type="text"
            value={saveRoot}
            placeholder={defaultRoot || "~/Desktop/ModelMaker3D"}
            onChange={(e) => setSaveRoot(e.target.value)}
          />
          <button type="button" className="dq-btn" style={{ whiteSpace: "nowrap" }} onClick={pickFolder}>
            選択
          </button>
        </div>
      </div>

      {/* モード切替 */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        <button className={`dq-tab ${mode === "image" ? "active" : ""}`} onClick={() => setMode("image")}>
          画像から
        </button>
        <button className={`dq-tab ${mode === "multiview" ? "active" : ""}`} onClick={() => setMode("multiview")}>
          複数視点から
        </button>
        <button className={`dq-tab ${mode === "text" ? "active" : ""}`} onClick={() => setMode("text")}>
          テキストから
        </button>
      </div>

      <div className="dq-frame" style={{ marginBottom: 20 }}>
        {mode === "text" ? (
          <>
            <label className="dq-label">作りたいもの（テキスト）</label>
            <textarea
              value={textPrompt}
              placeholder="例: かわいいキノコのキャラクター ／ 木製の椅子 ／ SFのドローン"
              onChange={(e) => setTextPrompt(e.target.value)}
            />
            <p className="dq-hint">Codexがコンセプト画像を生成 → TripoSRで立体化 → テクスチャを生成して貼ります。</p>
          </>
        ) : mode === "multiview" ? (
          <>
            <label className="dq-label">複数視点の画像（正面・横・後ろ など 2枚以上）</label>
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => onPickImages(Array.from(e.target.files || []))}
            />
            {images.length > 0 && (
              <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                {images.map((f, i) => (
                  <div key={i} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="dq-hint" style={{ flex: "1 1 220px", margin: 0, opacity: 0.9 }}>
                      {f.name}
                    </span>
                    <select
                      value={viewLabels[i] || "front"}
                      onChange={(e) => setLabelAt(i, e.target.value)}
                      style={{ flex: "0 0 160px" }}
                    >
                      {VIEW_OPTIONS.map((o) => (
                        <option key={o.v} value={o.v}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
            <p className="dq-hint">
              形状は「正面」の画像から作り、見た目は各方向の写真を実際にメッシュへ投影します。
              正面の写真を必ず1枚「正面」に設定してください。
            </p>
            <label className="dq-label" style={{ marginTop: 16 }}>形状の向き補正</label>
            <select value={frontAxis} onChange={(e) => setFrontAxis(e.target.value)}>
              {FRONT_AXIS_OPTIONS.map((o) => (
                <option key={o.v} value={o.v}>{o.label}</option>
              ))}
            </select>
            <p className="dq-hint" style={{ marginTop: 6 }}>
              出来上がりで前後左右がズレていたら、ここを変えて再生成してください。
            </p>
          </>
        ) : (
          <>
            <label className="dq-label">画像（1枚）</label>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => onPickImages(Array.from(e.target.files || []))}
            />
            {images.length > 0 && (
              <p className="dq-hint">選択中: {images.map((f) => f.name).join(", ")}</p>
            )}
            <label className="dq-label" style={{ marginTop: 18 }}>
              対象の説明（任意・テクスチャの精度が上がります）
            </label>
            <input
              type="text"
              value={subjectDesc}
              placeholder="例: 赤い木製の椅子 ／ 緑色のドラゴンのフィギュア"
              onChange={(e) => setSubjectDesc(e.target.value)}
            />
          </>
        )}

        {/* 詳細設定 */}
        <div style={{ display: "flex", gap: 16, marginTop: 18, flexWrap: "wrap" }}>
          {mode !== "multiview" && (
            <div style={{ flex: "1 1 240px" }}>
              <label className="dq-label">テクスチャの貼り方</label>
              <select value={uvMode} onChange={(e) => setUvMode(e.target.value)}>
                {UV_OPTIONS.map((o) => (
                  <option key={o.v} value={o.v}>{o.label}</option>
                ))}
              </select>
            </div>
          )}
          <div style={{ flex: "1 1 200px" }}>
            <label className="dq-label">メッシュの細かさ: {mcResolution}</label>
            <input
              type="range"
              min={128}
              max={320}
              step={32}
              value={mcResolution}
              onChange={(e) => setMcResolution(Number(e.target.value))}
            />
            <p className="dq-hint" style={{ marginTop: 6 }}>高いほど精細ですが遅くなります（推奨256）</p>
          </div>
        </div>

        <div style={{ marginTop: 22, display: "flex", gap: 12 }}>
          {!running ? (
            <button className="dq-btn" onClick={run}>生成開始</button>
          ) : (
            <button className="dq-btn" onClick={stop}>中断（{elapsed}秒）</button>
          )}
        </div>
      </div>

      {/* ログ */}
      {(logs.length > 0 || agentMsg) && (
        <div className="dq-frame" style={{ marginBottom: 20 }}>
          <label className="dq-label">進捗 {running ? `（${elapsed}秒）` : ""}</label>
          <div className="dq-log">
            {logs.map((l, i) => (
              <div key={i} className={
                l.kind === "error" ? "err" :
                l.kind === "done" ? "done" :
                l.kind === "cmd" || l.kind === "command" || l.kind === "command-ok" ? "cmd" :
                l.kind === "agent" ? "agent" : ""
              }>
                {l.text}
              </div>
            ))}
            {agentMsg && <div className="agent" style={{ marginTop: 8 }}>💬 {agentMsg}</div>}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {/* 結果 */}
      {result && (
        <div className="dq-frame">
          <label className="dq-label">完成した3Dモデル</label>
          {/* @ts-expect-error model-viewer is a web component */}
          <model-viewer
            src={result.modelUrl}
            alt="generated 3D model"
            camera-controls
            auto-rotate
            shadow-intensity="1"
            exposure="1"
          />
          <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
            <a className="dq-btn" href={result.modelUrl} download="model.glb">GLB をダウンロード</a>
            {result.fbxUrl && <a className="dq-btn" href={result.fbxUrl} download="model.fbx">FBX をダウンロード</a>}
            {result.objUrl && <a className="dq-btn" href={result.objUrl} download="mesh.obj">OBJ をダウンロード</a>}
          </div>
          {result.textureUrl && (
            <div style={{ marginTop: 18 }}>
              <label className="dq-label">テクスチャ（Codex画像生成）</label>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={result.textureUrl} alt="texture" style={{ maxWidth: 256, border: "3px solid #fff" }} />
            </div>
          )}
          <p className="dq-hint">保存先: {result.savedTo}</p>
        </div>
      )}
    </main>
  );
}
