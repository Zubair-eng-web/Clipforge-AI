"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Loader2, Plus, Save, Trash2, Type } from "lucide-react";
import { API, api, rows } from "@/lib/api8";

type Cfg = {
  font: string; font_size: number; scale: number; primary: string; secondary: string; outline_color: string;
  outline: number; shadow: number; bold: boolean; italic: boolean; uppercase: boolean; position: string;
  align: string; spacing: number; words_per_line: number; mode: string; animation: string; offset: number;
  margin_pct: number;
};
type Preset = { id: string; label: string; config: Cfg };
type Clip = { id: number; title: string; status: string };
type Line = { start: number; end: number; text: string };
type Overlay = { text: string; start: number; end: number; position: "top" | "center" | "bottom" };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
async function waitJob(id: number): Promise<void> {
  for (;;) {
    await sleep(2000);
    const j = await api(`/api/jobs/${id}`);
    if (j.status === "failed" || j.status === "cancelled") throw new Error(j.error ? String(j.error) : `Job ${j.status}`);
    if (j.status !== "queued" && j.status !== "processing") return;
  }
}
const LANGS: [string, string][] = [["auto", "Auto detect"], ["en", "English"], ["ur", "Urdu"], ["hi", "Hindi"], ["ar", "Arabic"], ["es", "Spanish"], ["fr", "French"]];
const box = "rounded-xl border border-slate-700 bg-slate-900/60 p-4 space-y-3";
const inp = "rounded bg-slate-800 p-1.5 text-sm";

export default function CaptionsStudioPage() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [fonts, setFonts] = useState<string[]>([]);
  const [presetId, setPresetId] = useState("gaming");
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [ovText, setOvText] = useState("");
  const [ovStart, setOvStart] = useState(0);
  const [ovEnd, setOvEnd] = useState(3);
  const [ovPos, setOvPos] = useState<Overlay["position"]>("center");
  const [lang, setLang] = useState("auto");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [t, setT] = useState(1);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [burned, setBurned] = useState<number | null>(null);

  const loadLines = useCallback(async (id: number) => {
    try {
      const d = await api(`/api/clips/${id}/captions`);
      setLines((d.lines as Line[]).map((l) => ({ start: l.start, end: l.end, text: l.text })));
    } catch {
      setLines([]);
    }
  }, []);

  useEffect(() => {
    api("/api/clips?limit=500")
      .then((d) => {
        const l = (rows(d) as Clip[]).filter((c) => c.status === "ready");
        setClips(l);
        if (l.length) setClipId(l[0].id);
      })
      .catch(() => setMsg("Backend se connect nahi ho raha. .\\scripts\\start-all.ps1 chalayein."));
  }, []);

  useEffect(() => {
    if (clipId === null) return;
    setBurned(null); setMsg(""); setPreviewUrl(null);
    loadLines(clipId);
    if (!presets.length) {
      api(`/api/clips/${clipId}/captions/presets`)
        .then((d) => {
          const ps = d.presets as Preset[];
          setPresets(ps);
          setFonts(d.fonts as string[]);
          const p = ps.find((x) => x.id === "gaming") ?? ps[0];
          setPresetId(p.id);
          setCfg(p.config);
        })
        .catch(() => setMsg("Presets load nahi hue."));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipId]);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label); setMsg("");
    try { await fn(); } catch (e) { setMsg(e instanceof Error ? e.message : "Error"); } finally { setBusy(""); }
  }
  const set = <K extends keyof Cfg>(k: K, v: Cfg[K]) => setCfg((c) => (c ? { ...c, [k]: v } : c));
  const pick = (p: Preset) => { setPresetId(p.id); setCfg(p.config); };
  const studioBody = () => ({ preset: presetId, config: cfg, overlays });

  function generate() {
    if (clipId === null) return;
    run("Captions ban rahe hain (Whisper)...", async () => {
      const r = await api(`/api/clips/${clipId}/captions/generate`, { method: "POST", body: JSON.stringify({ language: lang === "auto" ? null : lang }) });
      await waitJob(r.job_id);
      await loadLines(clipId);
      setMsg("Captions ready.");
    });
  }
  function saveLines() {
    if (clipId === null) return;
    run("Saving...", async () => {
      await api(`/api/clips/${clipId}/captions`, { method: "PUT", body: JSON.stringify({ lines }) });
      setMsg("Saved. Edit ki hui line ka word timing chala jata hai (karaoke us line par normal ho jayega).");
    });
  }
  function preview() {
    if (clipId === null || !cfg) return;
    run("Preview ban raha hai...", async () => {
      const r = await fetch(`${API}/api/clips/${clipId}/captions/studio-preview`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...studioBody(), t }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(typeof d.detail === "string" ? d.detail : "Preview failed");
      }
      const blob = await r.blob();
      setPreviewUrl((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
    });
  }
  function burn() {
    if (clipId === null || !cfg) return;
    run("Captions video mein burn ho rahe hain...", async () => {
      const r = await api(`/api/clips/${clipId}/captions/studio-burn`, { method: "POST", body: JSON.stringify(studioBody()) });
      await waitJob(r.job_id);
      setBurned(r.clip_id as number);
      setMsg("Done. Naya clip ban gaya (original safe hai).");
    });
  }
  const updLine = (i: number, patch: Partial<Line>) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const addOverlay = () => {
    if (!ovText.trim()) return;
    setOverlays((o) => [...o, { text: ovText.trim(), start: ovStart, end: Math.max(ovEnd, ovStart + 0.5), position: ovPos }]);
    setOvText("");
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Type className="h-7 w-7 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold">Captions Studio</h1>
          <p className="text-sm text-slate-400">Presets, custom style, word-by-word / karaoke, text overlays, SRT / VTT / ASS / burned MP4.</p>
        </div>
      </div>
      {msg && <div className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">{msg}</div>}
      {busy && <div className="flex items-center gap-2 text-sm text-violet-300"><Loader2 className="h-4 w-4 animate-spin" /> {busy}</div>}

      <div className={box}>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-300">Clip</label>
          <select className={inp} value={clipId ?? ""} onChange={(e) => setClipId(Number(e.target.value))}>
            {clips.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <label className="text-sm text-slate-300">Language</label>
          <select className={inp} value={lang} onChange={(e) => setLang(e.target.value)}>
            {LANGS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <button disabled={!!busy || clipId === null} onClick={generate} className="rounded bg-violet-600 px-3 py-1.5 text-sm font-semibold disabled:opacity-50">Generate captions</button>
        </div>
        {!clips.length && <p className="text-sm text-slate-400">Pehle koi clip banayein (Gaming Highlights / Manual Clipper).</p>}
        {clipId !== null && <video key={clipId} src={`${API}/api/clips/${clipId}/stream`} controls className="max-h-72 rounded bg-black" />}
      </div>

      {cfg && (
        <div className={box}>
          <div className="text-sm font-semibold">Style preset</div>
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => (
              <button key={p.id} onClick={() => pick(p)} className={`rounded-full border px-3 py-1 text-xs ${presetId === p.id ? "border-violet-400 bg-violet-500/30" : "border-slate-600 text-slate-300"}`}>{p.label}</button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <label className="space-y-1"><span className="block text-xs text-slate-400">Font</span>
              <select className={inp + " w-full"} value={cfg.font} onChange={(e) => set("font", e.target.value)}>
                {(fonts.includes(cfg.font) ? fonts : [cfg.font, ...fonts]).map((f) => <option key={f}>{f}</option>)}
              </select></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Size scale {cfg.scale.toFixed(2)}</span>
              <input type="range" min={0.4} max={3} step={0.05} value={cfg.scale} onChange={(e) => set("scale", Number(e.target.value))} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Mode</span>
              <select className={inp + " w-full"} value={cfg.mode} onChange={(e) => set("mode", e.target.value)}>
                <option value="line">Normal lines</option><option value="word">Word-by-word</option><option value="karaoke">Karaoke highlight</option>
              </select></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Words per line</span>
              <input type="number" min={1} max={12} className={inp + " w-full"} value={cfg.words_per_line} onChange={(e) => set("words_per_line", Number(e.target.value))} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Text / highlight colour</span>
              <input type="color" value={cfg.primary.toLowerCase()} onChange={(e) => set("primary", e.target.value)} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Base colour (karaoke)</span>
              <input type="color" value={cfg.secondary.toLowerCase()} onChange={(e) => set("secondary", e.target.value)} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Outline colour</span>
              <input type="color" value={cfg.outline_color.toLowerCase()} onChange={(e) => set("outline_color", e.target.value)} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Outline {cfg.outline}</span>
              <input type="range" min={0} max={12} step={0.5} value={cfg.outline} onChange={(e) => set("outline", Number(e.target.value))} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Shadow {cfg.shadow}</span>
              <input type="range" min={0} max={10} step={0.5} value={cfg.shadow} onChange={(e) => set("shadow", Number(e.target.value))} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Position</span>
              <select className={inp + " w-full"} value={cfg.position} onChange={(e) => set("position", e.target.value)}>
                <option value="bottom">Bottom</option><option value="center">Center</option><option value="top">Top</option>
              </select></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Alignment</span>
              <select className={inp + " w-full"} value={cfg.align} onChange={(e) => set("align", e.target.value)}>
                <option value="left">Left</option><option value="center">Center</option><option value="right">Right</option>
              </select></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Animation</span>
              <select className={inp + " w-full"} value={cfg.animation} onChange={(e) => set("animation", e.target.value)}>
                <option value="none">None</option><option value="fade">Fade</option><option value="pop">Pop</option>
              </select></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Letter spacing</span>
              <input type="number" step={0.5} className={inp + " w-full"} value={cfg.spacing} onChange={(e) => set("spacing", Number(e.target.value))} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Timing offset (s)</span>
              <input type="number" step={0.1} className={inp + " w-full"} value={cfg.offset} onChange={(e) => set("offset", Number(e.target.value))} /></label>
            <label className="space-y-1"><span className="block text-xs text-slate-400">Edge margin %</span>
              <input type="number" min={0} max={40} className={inp + " w-full"} value={cfg.margin_pct} onChange={(e) => set("margin_pct", Number(e.target.value))} /></label>
            <div className="flex items-end gap-4 text-xs">
              <label className="flex items-center gap-1"><input type="checkbox" checked={cfg.bold} onChange={(e) => set("bold", e.target.checked)} /> Bold</label>
              <label className="flex items-center gap-1"><input type="checkbox" checked={cfg.italic} onChange={(e) => set("italic", e.target.checked)} /> Italic</label>
              <label className="flex items-center gap-1"><input type="checkbox" checked={cfg.uppercase} onChange={(e) => set("uppercase", e.target.checked)} /> CAPS</label>
            </div>
          </div>
        </div>
      )}

      <div className={box}>
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">Caption lines ({lines.length})</span>
          <button disabled={!!busy || !lines.length} onClick={saveLines} className="inline-flex items-center gap-1 rounded bg-slate-700 px-3 py-1 text-xs disabled:opacity-40"><Save className="h-3 w-3" /> Save edits</button>
        </div>
        {!lines.length && <p className="text-sm text-slate-400">Abhi captions nahi hain. &quot;Generate captions&quot; dabayein. Bina bolne wale gameplay ke liye neeche text overlay use karein.</p>}
        <div className="max-h-64 space-y-1 overflow-y-auto">
          {lines.map((l, i) => (
            <div key={i} className="flex items-center gap-2">
              <input type="number" step={0.1} className={inp + " w-20"} value={l.start} onChange={(e) => updLine(i, { start: Number(e.target.value) })} />
              <input type="number" step={0.1} className={inp + " w-20"} value={l.end} onChange={(e) => updLine(i, { end: Number(e.target.value) })} />
              <input className={inp + " flex-1"} value={l.text} onChange={(e) => updLine(i, { text: e.target.value })} />
              <button onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))} className="text-slate-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
      </div>

      <div className={box}>
        <div className="text-sm font-semibold">Manual text overlays (gameplay without speech)</div>
        <div className="flex flex-wrap items-center gap-2">
          <input className={inp + " min-w-[200px] flex-1"} placeholder="Text (jaise: BOSS FIGHT)" value={ovText} onChange={(e) => setOvText(e.target.value)} maxLength={200} />
          <input type="number" step={0.5} className={inp + " w-20"} value={ovStart} onChange={(e) => setOvStart(Number(e.target.value))} />
          <input type="number" step={0.5} className={inp + " w-20"} value={ovEnd} onChange={(e) => setOvEnd(Number(e.target.value))} />
          <select className={inp} value={ovPos} onChange={(e) => setOvPos(e.target.value as Overlay["position"])}>
            <option value="top">Top</option><option value="center">Center</option><option value="bottom">Bottom</option>
          </select>
          <button onClick={addOverlay} className="inline-flex items-center gap-1 rounded bg-slate-700 px-3 py-1.5 text-xs"><Plus className="h-3 w-3" /> Add</button>
        </div>
        {overlays.map((o, i) => (
          <div key={i} className="flex items-center justify-between rounded bg-slate-800 px-3 py-1 text-xs">
            <span>{o.text} ({o.start}s - {o.end}s, {o.position})</span>
            <button onClick={() => setOverlays((x) => x.filter((_, j) => j !== i))} className="text-slate-500 hover:text-red-400"><Trash2 className="h-3 w-3" /></button>
          </div>
        ))}
      </div>

      <div className={box}>
        <div className="text-sm font-semibold">Preview and export</div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2">Preview at (s)
            <input type="number" min={0} step={0.5} className={inp + " w-20"} value={t} onChange={(e) => setT(Number(e.target.value))} /></label>
          <button disabled={!!busy || clipId === null || !cfg} onClick={preview} className="rounded bg-slate-700 px-3 py-1.5 text-xs disabled:opacity-40">Preview frame</button>
          <button disabled={!!busy || clipId === null || !cfg} onClick={burn} className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold disabled:opacity-40">Burn into video (new clip)</button>
        </div>
        {previewUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={previewUrl} alt="caption preview" className="max-h-96 rounded border border-slate-700" />
        )}
        {clipId !== null && (
          <div className="flex flex-wrap gap-2 text-xs">
            <a className="inline-flex items-center gap-1 rounded bg-slate-700 px-3 py-1.5" href={`${API}/api/clips/${clipId}/captions.srt`}><Download className="h-3 w-3" /> SRT</a>
            <a className="inline-flex items-center gap-1 rounded bg-slate-700 px-3 py-1.5" href={`${API}/api/clips/${clipId}/captions.vtt`}><Download className="h-3 w-3" /> VTT</a>
            <a className="inline-flex items-center gap-1 rounded bg-slate-700 px-3 py-1.5" href={`${API}/api/clips/${clipId}/captions.ass?preset=${presetId}`}><Download className="h-3 w-3" /> ASS</a>
            {burned !== null && <a className="inline-flex items-center gap-1 rounded bg-violet-600 px-3 py-1.5" href={`${API}/api/clips/${burned}/download`}><Download className="h-3 w-3" /> Download captioned MP4</a>}
          </div>
        )}
      </div>
    </div>
  );
}