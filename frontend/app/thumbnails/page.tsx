"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Image as ImageIcon, Loader2, Save, Trash2 } from "lucide-react";
import { API, fmtClock, type ClipItem } from "@/lib/api";

type Thumb = { id: number; clip_id: number | null; title: string; created_at: string };

const PRESETS = [
  { label: "White / Black", color: "#ffffff", outline: "#000000" },
  { label: "Yellow / Black", color: "#ffe600", outline: "#000000" },
  { label: "Red / White", color: "#ff2d2d", outline: "#ffffff" },
];

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const out: string[] = [];
  for (const para of text.split("\n")) {
    const words = para.split(/\s+/).filter(Boolean);
    if (words.length === 0) continue;
    let line = words[0];
    for (let i = 1; i < words.length; i++) {
      const test = `${line} ${words[i]}`;
      if (ctx.measureText(test).width <= maxW) line = test;
      else { out.push(line); line = words[i]; }
    }
    out.push(line);
  }
  return out;
}

export default function ThumbnailStudioPage() {
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [t, setT] = useState(0.5);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [text, setText] = useState("");
  const [size, setSize] = useState(14);
  const [color, setColor] = useState("#ffffff");
  const [outline, setOutline] = useState("#000000");
  const [pos, setPos] = useState<"top" | "center" | "bottom">("bottom");
  const [shade, setShade] = useState(true);
  const [thumbs, setThumbs] = useState<Thumb[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const urlRef = useRef<string | null>(null);

  const selected = clips.find((c) => c.id === clipId) ?? null;

  const loadThumbs = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/thumbnails`);
      if (r.ok) setThumbs((await r.json()).items as Thumb[]);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/clips?limit=200`);
        if (!r.ok) throw new Error();
        const ready = ((await r.json()).items as ClipItem[]).filter((c) => c.status === "ready" && c.has_file);
        setClips(ready);
        if (ready.length) { setClipId(ready[0].id); setText(ready[0].title.toUpperCase()); }
      } catch { setOffline(true); }
    })();
    loadThumbs();
    return () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); };
  }, [loadThumbs]);

  useEffect(() => {
    if (clipId === null) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/api/clips/${clipId}/frame?t=${t}`);
        if (!r.ok) throw new Error();
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const im = new Image();
        im.onload = () => {
          if (cancelled) { URL.revokeObjectURL(url); return; }
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          urlRef.current = url;
          setImg(im);
        };
        im.src = url;
      } catch {
        if (!cancelled) setMsg("Could not load a frame from this clip.");
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [clipId, t]);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c || !img) return;
    c.width = img.naturalWidth;
    c.height = img.naturalHeight;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const W = c.width, H = c.height;
    ctx.drawImage(img, 0, 0);

    if (shade) {
      if (pos === "center") {
        ctx.fillStyle = "rgba(0,0,0,0.35)";
        ctx.fillRect(0, 0, W, H);
      } else {
        const g = ctx.createLinearGradient(0, pos === "bottom" ? H : 0, 0, pos === "bottom" ? H * 0.45 : H * 0.55);
        g.addColorStop(0, "rgba(0,0,0,0.75)");
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
      }
    }

    const content = text.trim();
    if (!content) return;
    const fs = Math.round((Math.min(W, H) * size) / 100);
    ctx.font = `900 ${fs}px Impact, "Arial Black", "Segoe UI", sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.lineJoin = "round";
    const lines = wrapLines(ctx, content, W * 0.9);
    const lh = fs * 1.12;
    const block = lines.length * lh;
    const margin = H * 0.06;
    let y = pos === "top" ? margin : pos === "bottom" ? H - block - margin : (H - block) / 2;
    ctx.lineWidth = fs * 0.14;
    ctx.strokeStyle = outline;
    ctx.fillStyle = color;
    for (const line of lines) {
      ctx.strokeText(line, W / 2, y);
      ctx.fillText(line, W / 2, y);
      y += lh;
    }
  }, [img, text, size, color, outline, pos, shade]);

  function toBlob(): Promise<Blob | null> {
    return new Promise((res) => {
      const c = canvasRef.current;
      if (!c) return res(null);
      c.toBlob((b) => res(b), "image/jpeg", 0.92);
    });
  }

  async function save() {
    const blob = await toBlob();
    if (!blob) return;
    setBusy(true);
    setMsg("");
    try {
      const fd = new FormData();
      fd.append("file", blob, "thumbnail.jpg");
      fd.append("title", text.replace(/\s+/g, " ").trim().slice(0, 200));
      if (clipId !== null) fd.append("clip_id", String(clipId));
      const r = await fetch(`${API}/api/thumbnails`, { method: "POST", body: fd });
      const d = await r.json().catch(() => ({}));
      setMsg(r.ok ? "Saved to your thumbnail library." : typeof d.detail === "string" ? d.detail : "Could not save.");
      if (r.ok) loadThumbs();
    } catch {
      setMsg("Cannot reach the backend. Is it running?");
    } finally {
      setBusy(false);
    }
  }

  async function downloadNow() {
    const blob = await toBlob();
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "thumbnail.jpg";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function remove(th: Thumb) {
    if (!window.confirm("Delete this thumbnail?")) return;
    await fetch(`${API}/api/thumbnails/${th.id}`, { method: "DELETE" }).catch(() => null);
    loadThumbs();
  }

  return (
    <div className="max-w-6xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><ImageIcon size={24} className="text-violet-400" /> Thumbnail Studio</h1>
      <p className="text-sm text-zinc-400">Pick any frame of a clip, add text, then save it to your library or download it.</p>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}
      {!offline && clips.length === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-700 p-10 text-center text-sm text-zinc-400">
          No ready clips yet. Create a clip first (Manual Clipper or AI Auto Clipper).
        </div>
      )}

      {clips.length > 0 && (
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-1">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Clip</p>
              <select
                value={clipId ?? ""}
                onChange={(e) => { setClipId(Number(e.target.value)); setT(0.5); }}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
              >
                {clips.map((c) => <option key={c.id} value={c.id}>{c.title} ({fmtClock(c.duration_sec)})</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Frame time: {t.toFixed(1)}s</p>
              <input
                type="range" min={0} max={Math.max(selected?.duration_sec ?? 1, 0.1)} step={0.1} value={t}
                onChange={(e) => setT(Number(e.target.value))} className="w-full"
              />
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Text</p>
              <textarea
                value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={120}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-violet-500"
              />
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Text size: {size}%</p>
              <input type="range" min={5} max={26} step={1} value={size} onChange={(e) => setSize(Number(e.target.value))} className="w-full" />
            </div>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((p) => (
                <button key={p.label} onClick={() => { setColor(p.color); setOutline(p.outline); }}
                  className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs hover:border-zinc-500">{p.label}</button>
              ))}
            </div>
            <div className="flex gap-2">
              {(["top", "center", "bottom"] as const).map((p) => (
                <button key={p} onClick={() => setPos(p)}
                  className={`flex-1 rounded-md border px-2 py-1 text-xs capitalize ${pos === p ? "border-violet-500 bg-violet-600/20 text-white" : "border-zinc-700 bg-zinc-900 text-zinc-300"}`}>{p}</button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              <input type="checkbox" checked={shade} onChange={(e) => setShade(e.target.checked)} /> Dark shade behind text
            </label>
            <div className="flex gap-2">
              <button onClick={save} disabled={busy || !img}
                className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
                {busy ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save
              </button>
              <button onClick={downloadNow} disabled={!img}
                className="inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm hover:bg-zinc-700 disabled:opacity-50">
                <Download size={16} /> Download
              </button>
            </div>
            {msg && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}
          </div>

          <div className="lg:col-span-2">
            <div className="flex min-h-64 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-2">
              {!img && <Loader2 className="animate-spin text-violet-400" />}
              <canvas ref={canvasRef} className={`max-h-[70vh] max-w-full rounded ${img ? "" : "hidden"}`} />
            </div>
          </div>
        </div>
      )}

      <h2 className="mt-10 font-semibold text-white">Saved thumbnails</h2>
      {thumbs.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-500">Nothing saved yet.</p>
      ) : (
        <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {thumbs.map((th) => (
            <div key={th.id} className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`${API}/api/thumbnails/${th.id}/file`} alt={th.title} className="h-36 w-full object-cover" />
              <div className="flex items-center justify-between p-2">
                <span className="truncate text-xs text-zinc-400">{th.title || "Untitled"}</span>
                <div className="flex gap-1">
                  <a href={`${API}/api/thumbnails/${th.id}/download`} className="rounded-md bg-zinc-800 p-1.5 hover:bg-zinc-700" title="Download"><Download size={14} /></a>
                  <button onClick={() => remove(th)} className="rounded-md bg-zinc-800 p-1.5 text-red-400 hover:bg-red-950" title="Delete"><Trash2 size={14} /></button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}