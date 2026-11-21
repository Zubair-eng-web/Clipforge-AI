"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Image as ImageIcon, Loader2, Save, Sparkles, Trash2 } from "lucide-react";
import { API, fmtClock, type ClipItem } from "@/lib/api";

type Thumb = { id: number; clip_id: number | null; title: string; created_at: string };
type Plat = { label: string; w: number; h: number };
type Sug = { t: number; score: number };

const FALLBACK: Record<string, Plat> = {
  youtube: { label: "YouTube (1280x720)", w: 1280, h: 720 },
  shorts: { label: "Shorts / Reels / TikTok cover (1080x1920)", w: 1080, h: 1920 },
  instagram_post: { label: "Instagram post (1080x1080)", w: 1080, h: 1080 },
};
const COLORS = [
  { label: "White / Black", color: "#ffffff", outline: "#000000" },
  { label: "Yellow / Black", color: "#ffe600", outline: "#000000" },
  { label: "Red / White", color: "#ff2d2d", outline: "#ffffff" },
];
const FONTS = ["Impact", "Arial Black", "Segoe UI", "Georgia"];
const box = "w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white";
const lab = "mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500";

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
  const [plats, setPlats] = useState<Record<string, Plat>>(FALLBACK);
  const [platform, setPlatform] = useState("youtube");
  const [mode, setMode] = useState<"fill" | "blur">("fill");
  const [zoom, setZoom] = useState(1);
  const [fx, setFx] = useState(0.5);
  const [fy, setFy] = useState(0.5);
  const [blurPx, setBlurPx] = useState(30);
  const [bri, setBri] = useState(0);
  const [con, setCon] = useState(100);
  const [sat, setSat] = useState(100);
  const [vignette, setVignette] = useState(false);
  const [text, setText] = useState("");
  const [font, setFont] = useState("Impact");
  const [size, setSize] = useState(14);
  const [color, setColor] = useState("#ffffff");
  const [outline, setOutline] = useState("#000000");
  const [pos, setPos] = useState<"top" | "center" | "bottom">("bottom");
  const [shade, setShade] = useState(true);
  const [fmt, setFmt] = useState<"jpg" | "png">("jpg");
  const [sugFrames, setSugFrames] = useState<Sug[]>([]);
  const [sugTexts, setSugTexts] = useState<string[]>([]);
  const [sugNote, setSugNote] = useState("");
  const [sugBusy, setSugBusy] = useState(false);
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
      try {
        const r = await fetch(`${API}/api/thumbnails/platforms`);
        if (r.ok) setPlats((await r.json()).platforms as Record<string, Plat>);
      } catch { /* keep fallback */ }
    })();
    loadThumbs();
    return () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); };
  }, [loadThumbs]);

  useEffect(() => {
    if (clipId === null) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/api/clips/${clipId}/frame?t=${t}&size=1920`);
        if (!r.ok) throw new Error();
        const url = URL.createObjectURL(await r.blob());
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
    const P = plats[platform] ?? { label: "", w: 1280, h: 720 };
    const W = P.w, H = P.h;
    c.width = W;
    c.height = H;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const cf = ctx as unknown as { filter: string };
    const iw = img.naturalWidth, ih = img.naturalHeight;
    const adjust = `brightness(${100 + bri}%) contrast(${con}%) saturate(${sat}%)`;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);
    const place = (s: number) => {
      const dw = iw * s, dh = ih * s;
      const x = dw >= W ? (W - dw) * fx : (W - dw) / 2;
      const y = dh >= H ? (H - dh) * fy : (H - dh) / 2;
      ctx.drawImage(img, x, y, dw, dh);
    };
    if (mode === "blur") {
      cf.filter = `blur(${blurPx}px) ${adjust}`;
      place(Math.max(W / iw, H / ih) * 1.15);
      cf.filter = adjust;
      place(Math.min(W / iw, H / ih) * zoom);
    } else {
      cf.filter = adjust;
      place(Math.max(W / iw, H / ih) * zoom);
    }
    cf.filter = "none";

    if (vignette) {
      const g = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.max(W, H) * 0.75);
      g.addColorStop(0, "rgba(0,0,0,0)");
      g.addColorStop(1, "rgba(0,0,0,0.6)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
    }
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
    ctx.font = `900 ${fs}px "${font}", Impact, "Arial Black", sans-serif`;
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
  }, [img, plats, platform, mode, zoom, fx, fy, blurPx, bri, con, sat, vignette, text, font, size, color, outline, pos, shade]);

  function toBlob(): Promise<Blob | null> {
    return new Promise((res) => {
      const c = canvasRef.current;
      if (!c) return res(null);
      if (fmt === "png") c.toBlob((b) => res(b), "image/png");
      else c.toBlob((b) => res(b), "image/jpeg", 0.92);
    });
  }

  async function suggest() {
    if (clipId === null) return;
    setSugBusy(true); setMsg("");
    try {
      const r = await fetch(`${API}/api/thumbnails/suggest`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clip_id: clipId, count: 6 }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { setMsg(typeof d.detail === "string" ? d.detail : "Suggestion failed."); }
      else {
        setSugFrames(d.frames as Sug[]);
        setSugTexts(d.texts as string[]);
        setSugNote(d.warning ? String(d.warning) : d.source === "gemini" ? "Text ideas by Gemini (title and description only)." : "");
        if ((d.frames as Sug[]).length) setT((d.frames as Sug[])[0].t);
      }
    } catch { setMsg("Cannot reach the backend. Is it running?"); }
    setSugBusy(false);
  }

  async function save() {
    const blob = await toBlob();
    if (!blob) return;
    setBusy(true); setMsg("");
    try {
      const fd = new FormData();
      fd.append("file", blob, `thumbnail.${fmt}`);
      fd.append("title", text.replace(/\s+/g, " ").trim().slice(0, 200));
      if (clipId !== null) fd.append("clip_id", String(clipId));
      const r = await fetch(`${API}/api/thumbnails`, { method: "POST", body: fd });
      const d = await r.json().catch(() => ({}));
      setMsg(r.ok ? "Saved to your thumbnail library." : typeof d.detail === "string" ? d.detail : "Could not save.");
      if (r.ok) loadThumbs();
    } catch { setMsg("Cannot reach the backend. Is it running?"); }
    setBusy(false);
  }

  async function downloadNow() {
    const blob = await toBlob();
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `thumbnail.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function remove(th: Thumb) {
    if (!window.confirm("Delete this thumbnail?")) return;
    await fetch(`${API}/api/thumbnails/${th.id}`, { method: "DELETE" }).catch(() => null);
    loadThumbs();
  }

  const sl = (label: string, v: number, min: number, max: number, step: number, set: (n: number) => void) => (
    <label className="block text-xs text-zinc-400">{label}: <span className="text-zinc-200">{v}</span>
      <input type="range" min={min} max={max} step={step} value={v} onChange={(e) => set(Number(e.target.value))} className="w-full" /></label>
  );

  return (
    <div className="max-w-7xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><ImageIcon size={24} className="text-violet-400" /> Thumbnail Studio</h1>
      <p className="text-sm text-zinc-400">AI frame suggestions, platform sizes, crop, background effects, text, and PNG or JPG export.</p>

      {offline && <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">Backend is offline. Start it with <code>.\scripts\start-all.ps1</code></div>}
      {!offline && clips.length === 0 && <div className="mt-6 rounded-xl border border-dashed border-zinc-700 p-10 text-center text-sm text-zinc-400">No ready clips yet. Create a clip first.</div>}

      {clips.length > 0 && (
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="space-y-4">
            <div>
              <p className={lab}>Clip</p>
              <select value={clipId ?? ""} onChange={(e) => { setClipId(Number(e.target.value)); setT(0.5); setSugFrames([]); setSugTexts([]); }} className={box}>
                {clips.map((c) => <option key={c.id} value={c.id}>{c.title} ({fmtClock(c.duration_sec)})</option>)}
              </select>
            </div>
            <div>
              <p className={lab}>Frame time: {t.toFixed(1)}s</p>
              <input type="range" min={0} max={Math.max(selected?.duration_sec ?? 1, 0.1)} step={0.1} value={t} onChange={(e) => setT(Number(e.target.value))} className="w-full" />
            </div>
            <button onClick={suggest} disabled={sugBusy || clipId === null}
              className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
              {sugBusy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} AI suggest best frames and text
            </button>
            <p className="text-xs text-amber-400">With a Gemini key, only the clip title and scene description (text) are sent. No video frames.</p>
            {sugFrames.length > 0 && (
              <div>
                <p className={lab}>Best frames (click to use)</p>
                <div className="grid grid-cols-3 gap-2">
                  {sugFrames.map((f) => (
                    <button key={f.t} onClick={() => setT(f.t)} className={`overflow-hidden rounded border ${Math.abs(f.t - t) < 0.05 ? "border-violet-500" : "border-zinc-700"}`}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={`${API}/api/clips/${clipId}/frame?t=${f.t}&size=320`} alt="" className="w-full" />
                      <div className="text-[10px] text-zinc-400">{f.t}s - {f.score}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {sugTexts.length > 0 && (
              <div>
                <p className={lab}>Text ideas (click to use)</p>
                <div className="flex flex-wrap gap-2">
                  {sugTexts.map((s) => <button key={s} onClick={() => setText(s)} className="rounded-full border border-zinc-700 px-3 py-1 text-xs hover:border-violet-500">{s}</button>)}
                </div>
                {sugNote && <p className="mt-1 text-xs text-zinc-500">{sugNote}</p>}
              </div>
            )}
            <div>
              <p className={lab}>Text</p>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={120} className={box} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-zinc-400">Font
                <select value={font} onChange={(e) => setFont(e.target.value)} className={box}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select></label>
              <div>{sl("Text size %", size, 5, 26, 1, setSize)}</div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {COLORS.map((p) => <button key={p.label} onClick={() => { setColor(p.color); setOutline(p.outline); }} className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs hover:border-zinc-500">{p.label}</button>)}
              <label className="text-xs text-zinc-400">Text <input type="color" value={color} onChange={(e) => setColor(e.target.value)} /></label>
              <label className="text-xs text-zinc-400">Outline <input type="color" value={outline} onChange={(e) => setOutline(e.target.value)} /></label>
            </div>
            <div className="flex gap-2">
              {(["top", "center", "bottom"] as const).map((p) => (
                <button key={p} onClick={() => setPos(p)} className={`flex-1 rounded-md border px-2 py-1 text-xs capitalize ${pos === p ? "border-violet-500 bg-violet-600/20 text-white" : "border-zinc-700 bg-zinc-900 text-zinc-300"}`}>{p}</button>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <p className={lab}>Platform size</p>
              <select value={platform} onChange={(e) => setPlatform(e.target.value)} className={box}>
                {Object.entries(plats).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
              </select>
            </div>
            <div>
              <p className={lab}>Background</p>
              <div className="flex gap-2">
                {(["fill", "blur"] as const).map((m) => (
                  <button key={m} onClick={() => setMode(m)} className={`flex-1 rounded-md border px-2 py-1 text-xs ${mode === m ? "border-violet-500 bg-violet-600/20 text-white" : "border-zinc-700 bg-zinc-900 text-zinc-300"}`}>
                    {m === "fill" ? "Fill (crop)" : "Fit + blurred background"}</button>
                ))}
              </div>
            </div>
            {mode === "blur" && sl("Background blur", blurPx, 5, 80, 5, setBlurPx)}
            {sl("Zoom", zoom, mode === "blur" ? 0.5 : 1, 3, 0.05, setZoom)}
            {sl("Crop position: left to right", fx, 0, 1, 0.01, setFx)}
            {sl("Crop position: top to bottom", fy, 0, 1, 0.01, setFy)}
            <p className={lab}>Effects</p>
            {sl("Brightness", bri, -50, 50, 5, setBri)}
            {sl("Contrast %", con, 50, 150, 5, setCon)}
            {sl("Saturation %", sat, 0, 200, 5, setSat)}
            <label className="flex items-center gap-2 text-sm text-zinc-300"><input type="checkbox" checked={vignette} onChange={(e) => setVignette(e.target.checked)} /> Vignette (dark edges)</label>
            <label className="flex items-center gap-2 text-sm text-zinc-300"><input type="checkbox" checked={shade} onChange={(e) => setShade(e.target.checked)} /> Dark shade behind text</label>
            <div>
              <p className={lab}>Export format</p>
              <div className="flex gap-2">
                {(["jpg", "png"] as const).map((f) => (
                  <button key={f} onClick={() => setFmt(f)} className={`flex-1 rounded-md border px-2 py-1 text-xs uppercase ${fmt === f ? "border-violet-500 bg-violet-600/20 text-white" : "border-zinc-700 bg-zinc-900 text-zinc-300"}`}>{f}</button>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={save} disabled={busy || !img} className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
                {busy ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save</button>
              <button onClick={downloadNow} disabled={!img} className="inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm hover:bg-zinc-700 disabled:opacity-50"><Download size={16} /> Download</button>
            </div>
            {msg && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}
          </div>

          <div>
            <div className="flex min-h-64 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-2">
              {!img && <Loader2 className="animate-spin text-violet-400" />}
              <canvas ref={canvasRef} className={`max-h-[75vh] max-w-full rounded ${img ? "" : "hidden"}`} />
            </div>
            <p className="mt-1 text-xs text-zinc-500">Preview is scaled down. The saved file has the full platform size ({plats[platform]?.w}x{plats[platform]?.h}).</p>
          </div>
        </div>
      )}

      <h2 className="mt-10 font-semibold text-white">Saved thumbnails</h2>
      {thumbs.length === 0 ? <p className="mt-2 text-sm text-zinc-500">Nothing saved yet.</p> : (
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
