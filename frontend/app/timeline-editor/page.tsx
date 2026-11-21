"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Film, Loader2, Plus, RotateCcw, RotateCw, Scissors, Trash2 } from "lucide-react";
import { API, api, rows } from "@/lib/api8";
import { watchJob, type JobItem } from "@/lib/api";

type ClipRow = { id: number; title: string; status: string; duration_sec: number | null };
type Track = { id: number; name: string; duration_sec: number | null };
type Seg = { uid: number; clipId: number; start: number; end: number };
type Ov = { uid: number; text: string; start: number; end: number; position: "top" | "center" | "bottom" };
type Mu = { uid: number; trackId: number; volume: number; start: number; trimIn: number; trimOut: number | null; fadeIn: number; fadeOut: number; loop: boolean };
type Doc = { segs: Seg[]; transition: string; tsec: number; ratio: string; overlays: Ov[]; music: Mu[]; origOn: boolean; origVol: number };
type Hist = { past: Doc[]; present: Doc; future: Doc[] };

const EMPTY: Doc = { segs: [], transition: "none", tsec: 0.5, ratio: "first", overlays: [], music: [], origOn: true, origVol: 100 };
const TRANS = ["none", "fade", "fadeblack", "dissolve", "wipeleft", "slideleft", "circleopen"];
const r2 = (x: number) => Math.round(x * 100) / 100;
const num = (v: string, d = 0) => { const x = parseFloat(v); return Number.isFinite(x) ? x : d; };
const inp = "rounded bg-slate-800 border border-slate-700 p-1.5 text-sm";
const btn = "rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40 px-3 py-1.5 text-sm";

export default function TimelineEditorPage() {
  const [h, setH] = useState<Hist>({ past: [], present: EMPTY, future: [] });
  const d = h.present;
  const [clips, setClips] = useState<ClipRow[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [pickClip, setPickClip] = useState<number | null>(null);
  const [baseId, setBaseId] = useState<number | null>(null);
  const [splitAt, setSplitAt] = useState<Record<number, string>>({});
  const [color, setColor] = useState("#FFE600");
  const [upper, setUpper] = useState(false);
  const [anim, setAnim] = useState("none");
  const [job, setJob] = useState<JobItem | null>(null);
  const [kind, setKind] = useState("");
  const [resultId, setResultId] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const uid = useRef(1);
  const stop = useRef<(() => void) | null>(null);
  const running = job !== null && (job.status === "queued" || job.status === "processing");

  const nid = () => uid.current++;
  const upd = (fn: (x: Doc) => Doc, record = true) =>
    setH((p) => ({ past: record ? [...p.past, p.present].slice(-50) : p.past, present: fn(p.present), future: record ? [] : p.future }));
  const undo = useCallback(() => setH((p) => (p.past.length ? { past: p.past.slice(0, -1), present: p.past[p.past.length - 1], future: [p.present, ...p.future] } : p)), []);
  const redo = useCallback(() => setH((p) => (p.future.length ? { past: [...p.past, p.present], present: p.future[0], future: p.future.slice(1) } : p)), []);

  const loadClips = useCallback(async () => {
    try {
      const list = (rows(await api("/api/clips?limit=500")) as ClipRow[]).filter((c) => c.status === "ready");
      setClips(list);
      setPickClip((cur) => cur ?? (list.length ? list[0].id : null));
    } catch { setMsg("Backend not reachable. Start it with .\\scripts\\start-all.ps1"); }
  }, []);

  useEffect(() => {
    loadClips();
    api("/api/music").then((x) => setTracks(rows(x) as Track[])).catch(() => setTracks([]));
    return () => { if (stop.current) stop.current(); };
  }, [loadClips]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  const clipOf = (id: number) => clips.find((c) => c.id === id);
  const titleOf = (id: number) => clipOf(id)?.title ?? `Clip ${id}`;
  const dur = (s: Seg) => Math.max(s.end - s.start, 0);
  const sumDur = d.segs.reduce((a, s) => a + dur(s), 0);
  const t = d.transition !== "none" && d.segs.length > 1 ? d.tsec : 0;
  const total = r2(Math.max(sumDur - (d.segs.length - 1 > 0 ? d.segs.length - 1 : 0) * t, 0));
  const base = baseId !== null ? clipOf(baseId) : undefined;
  const scale = Math.max((base?.duration_sec ?? 0) || total, 1);
  const pct = (x: number) => `${Math.min(Math.max((x / scale) * 100, 0), 100)}%`;

  function addSeg() {
    const c = pickClip !== null ? clipOf(pickClip) : undefined;
    if (!c || d.segs.length >= 20) return;
    const end = Math.floor((c.duration_sec ?? 1) * 10) / 10;
    upd((x) => ({ ...x, segs: [...x.segs, { uid: nid(), clipId: c.id, start: 0, end }] }));
  }
  const setSeg = (id: number, p: Partial<Seg>, rec = true) =>
    upd((x) => ({ ...x, segs: x.segs.map((s) => (s.uid === id ? { ...s, ...p } : s)) }), rec);
  const moveSeg = (i: number, dir: number) =>
    upd((x) => {
      const j = i + dir;
      if (j < 0 || j >= x.segs.length) return x;
      const n = x.segs.slice();
      const tmp = n[i]; n[i] = n[j]; n[j] = tmp;
      return { ...x, segs: n };
    });
  function split(s: Seg, i: number) {
    const at = num(splitAt[s.uid] ?? "", (s.start + s.end) / 2);
    if (at < s.start + 0.3 || at > s.end - 0.3) { setMsg("Split point must be at least 0.3s inside the segment."); return; }
    setMsg("");
    upd((x) => {
      const n = x.segs.slice();
      if (n.length >= 20) return x;
      n.splice(i, 1, { ...s, end: r2(at) }, { uid: nid(), clipId: s.clipId, start: r2(at), end: s.end });
      return { ...x, segs: n };
    });
  }

  async function start(path: string, body: object, k: string) {
    setMsg(""); setResultId(null); setJob(null);
    try {
      const r = await api(path, { method: "POST", body: JSON.stringify(body) });
      const newId = r.clip_id as number;
      setKind(k); setResultId(newId);
      setJob({ id: r.job_id, type: "", video_id: null, status: "queued", progress: 0, error: null, created_at: "", updated_at: "" });
      if (stop.current) stop.current();
      stop.current = watchJob(r.job_id as number, (j) => {
        setJob(j);
        if (j.status === "completed") { loadClips(); if (k === "render") setBaseId(newId); }
        else if (j.status === "failed") setMsg("Failed: " + (j.error || "unknown error"));
      });
    } catch (e) { setMsg((e as Error).message); }
  }

  const render = () => start("/api/editor/timeline", {
    segments: d.segs.map((s) => ({ clip_id: s.clipId, start: s.start, end: s.end })),
    ratio: d.ratio, transition: d.transition, transition_sec: d.tsec,
  }, "render");

  const compose = () => {
    if (baseId === null) return;
    start("/api/editor/compose", {
      clip_id: baseId,
      overlays: d.overlays.filter((o) => o.text.trim()).map((o) => ({ text: o.text.trim(), start: o.start, end: o.end, position: o.position })),
      music: d.music.filter((m) => m.trackId > 0).map((m) => ({
        track_id: m.trackId, volume: m.volume, start_sec: m.start, trim_in: m.trimIn,
        trim_out: m.trimOut && m.trimOut > 0 ? m.trimOut : null, fade_in: m.fadeIn, fade_out: m.fadeOut, loop: m.loop,
      })),
      original_on: d.origOn, original_volume: d.origVol,
      style: { primary: color, uppercase: upper, animation: anim, bold: true, font_size: 0 },
    }, "compose");
  };

  const setOv = (id: number, p: Partial<Ov>, rec = true) =>
    upd((x) => ({ ...x, overlays: x.overlays.map((o) => (o.uid === id ? { ...o, ...p } : o)) }), rec);
  const setMu = (id: number, p: Partial<Mu>) =>
    upd((x) => ({ ...x, music: x.music.map((m) => (m.uid === id ? { ...m, ...p } : m)) }));

  const musicSpan = (m: Mu) => {
    const td = tracks.find((k) => k.id === m.trackId)?.duration_sec ?? 0;
    const room = Math.max(scale - m.start, 0);
    if (m.loop) return room;
    const seg = (m.trimOut && m.trimOut > 0 ? m.trimOut : td) - m.trimIn;
    return Math.min(room, seg > 0 ? seg : room);
  };

  const lab = "text-xs text-slate-400";
  return (
    <div className="p-6 space-y-5 max-w-7xl text-slate-200">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Film className="w-7 h-7 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold">Timeline Editor</h1>
            <p className="text-sm text-slate-400">Arrange segments, split, add transitions, text overlays and music tracks. Every result is a NEW clip.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className={btn} disabled={!h.past.length} onClick={undo}><RotateCcw className="inline w-4 h-4 mr-1" />Undo</button>
          <button className={btn} disabled={!h.future.length} onClick={redo}><RotateCw className="inline w-4 h-4 mr-1" />Redo</button>
        </div>
      </div>

      {msg && <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">{msg}</div>}

      <div className="rounded-xl border border-slate-700 p-3 space-y-2 bg-slate-900/50">
        <div className="text-xs text-slate-500">Timeline ({total}s)  -  Text and Audio tracks use the &quot;apply to&quot; clip length ({r2(scale)}s)</div>
        <div className="flex items-center gap-2"><span className="w-12 text-xs text-slate-400">Video</span>
          <div className="flex-1 flex h-8 rounded overflow-hidden bg-slate-800">
            {d.segs.map((s, i) => (
              <div key={s.uid} title={`${titleOf(s.clipId)} ${s.start}-${s.end}`}
                className={`h-8 text-[10px] flex items-center justify-center overflow-hidden border-r border-slate-900 ${i % 2 ? "bg-violet-700" : "bg-violet-600"}`}
                style={{ width: `${sumDur > 0 ? (dur(s) / sumDur) * 100 : 0}%` }}>{i + 1}</div>
            ))}
          </div></div>
        <div className="flex items-center gap-2"><span className="w-12 text-xs text-slate-400">Text</span>
          <div className="flex-1 relative h-6 rounded bg-slate-800">
            {d.overlays.map((o) => (
              <div key={o.uid} className="absolute top-0 h-6 bg-amber-600/80 text-[10px] px-1 overflow-hidden whitespace-nowrap rounded"
                style={{ left: pct(o.start), width: pct(Math.max(o.end - o.start, 0.1)) }}>{o.text}</div>
            ))}
          </div></div>
        <div className="flex items-center gap-2"><span className="w-12 text-xs text-slate-400">Audio</span>
          <div className="flex-1 relative rounded bg-slate-800" style={{ height: Math.max(24, d.music.length * 18) }}>
            {d.music.map((m, i) => (
              <div key={m.uid} className="absolute h-4 bg-emerald-600/80 text-[10px] px-1 overflow-hidden whitespace-nowrap rounded"
                style={{ top: i * 18 + 2, left: pct(m.start), width: pct(Math.max(musicSpan(m), 0.1)) }}>
                {tracks.find((k) => k.id === m.trackId)?.name ?? "track"}</div>
            ))}
          </div></div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="space-y-3">
          <h2 className="font-semibold">1. Video segments</h2>
          <div className="flex gap-2">
            <select className={inp + " flex-1"} value={pickClip ?? ""} onChange={(e) => setPickClip(Number(e.target.value))}>
              {clips.length === 0 && <option value="">No ready clips</option>}
              {clips.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.title} ({Math.round(c.duration_sec ?? 0)}s)</option>)}
            </select>
            <button className={btn} disabled={pickClip === null || d.segs.length >= 20} onClick={addSeg}><Plus className="inline w-4 h-4" /> Add</button>
          </div>
          {d.segs.length === 0 && <p className="text-sm text-slate-500">Add at least one segment.</p>}
          {d.segs.map((s, i) => (
            <div key={s.uid} className="rounded-lg border border-slate-700 p-2 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="truncate font-medium">{i + 1}. {titleOf(s.clipId)}</span>
                <span className="flex gap-1">
                  <button className="p-1 hover:bg-slate-700 rounded" onClick={() => moveSeg(i, -1)}><ArrowUp className="w-4 h-4" /></button>
                  <button className="p-1 hover:bg-slate-700 rounded" onClick={() => moveSeg(i, 1)}><ArrowDown className="w-4 h-4" /></button>
                  <button className="p-1 hover:bg-slate-700 rounded text-red-400" onClick={() => upd((x) => ({ ...x, segs: x.segs.filter((q) => q.uid !== s.uid) }))}><Trash2 className="w-4 h-4" /></button>
                </span>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <label className={lab}>Start<input type="number" step={0.1} min={0} className={inp + " w-20 block"} value={s.start} onChange={(e) => setSeg(s.uid, { start: num(e.target.value) })} /></label>
                <label className={lab}>End<input type="number" step={0.1} min={0} className={inp + " w-20 block"} value={s.end} onChange={(e) => setSeg(s.uid, { end: num(e.target.value) })} /></label>
                <label className={lab}>Split at<input type="number" step={0.1} className={inp + " w-20 block"} placeholder={String(r2((s.start + s.end) / 2))}
                  value={splitAt[s.uid] ?? ""} onChange={(e) => setSplitAt({ ...splitAt, [s.uid]: e.target.value })} /></label>
                <button className={btn} onClick={() => split(s, i)}><Scissors className="inline w-4 h-4" /> Split</button>
                <span className="text-xs text-slate-500">{r2(dur(s))}s</span>
              </div>
            </div>
          ))}
          <div className="grid grid-cols-3 gap-3">
            <label className={lab}>Transition
              <select className={inp + " w-full block"} value={d.transition} onChange={(e) => upd((x) => ({ ...x, transition: e.target.value }))}>
                {TRANS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select></label>
            <label className={lab}>Seconds {d.tsec}
              <input type="range" min={0.2} max={2} step={0.1} className="w-full block" value={d.tsec} disabled={d.transition === "none"}
                onChange={(e) => upd((x) => ({ ...x, tsec: num(e.target.value, 0.5) }))} /></label>
            <label className={lab}>Output size
              <select className={inp + " w-full block"} value={d.ratio} onChange={(e) => upd((x) => ({ ...x, ratio: e.target.value }))}>
                <option value="first">Same as first</option><option value="9:16">9:16 (720x1280)</option>
                <option value="1:1">1:1 (720x720)</option><option value="16:9">16:9 (1280x720)</option>
              </select></label>
          </div>
          <p className="text-xs text-slate-500">With a transition, every segment must be at least 2x the transition seconds.</p>
          <button disabled={running || d.segs.length === 0} onClick={render}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-5 py-2.5 font-medium">
            {running && kind === "render" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Film className="w-4 h-4" />} Render timeline
          </button>
        </div>

        <div className="space-y-3">
          <h2 className="font-semibold">2. Text overlays and music</h2>
          <label className={lab + " block"}>Apply to clip (the rendered timeline is selected automatically)
            <select className={inp + " w-full block"} value={baseId ?? ""} onChange={(e) => setBaseId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Choose a clip</option>
              {clips.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.title} ({Math.round(c.duration_sec ?? 0)}s)</option>)}
            </select></label>

          <div className="flex items-center justify-between"><span className="text-sm font-medium">Text overlays ({d.overlays.length}/30)</span>
            <button className={btn} disabled={d.overlays.length >= 30} onClick={() => upd((x) => ({ ...x, overlays: [...x.overlays, { uid: nid(), text: "", start: 0, end: 2, position: "center" }] }))}><Plus className="inline w-4 h-4" /> Add text</button></div>
          {d.overlays.map((o) => (
            <div key={o.uid} className="rounded-lg border border-slate-700 p-2 space-y-2 text-sm">
              <input className={inp + " w-full"} maxLength={200} placeholder="Text on screen" value={o.text} onChange={(e) => setOv(o.uid, { text: e.target.value }, false)} />
              <div className="flex flex-wrap items-end gap-3">
                <label className={lab}>Start<input type="number" step={0.1} min={0} className={inp + " w-20 block"} value={o.start} onChange={(e) => setOv(o.uid, { start: num(e.target.value) })} /></label>
                <label className={lab}>End<input type="number" step={0.1} min={0} className={inp + " w-20 block"} value={o.end} onChange={(e) => setOv(o.uid, { end: num(e.target.value) })} /></label>
                <label className={lab}>Position
                  <select className={inp + " block"} value={o.position} onChange={(e) => setOv(o.uid, { position: e.target.value as Ov["position"] })}>
                    <option value="top">top</option><option value="center">center</option><option value="bottom">bottom</option></select></label>
                <button className="p-1 text-red-400 hover:bg-slate-700 rounded" onClick={() => upd((x) => ({ ...x, overlays: x.overlays.filter((q) => q.uid !== o.uid) }))}><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          ))}
          {d.overlays.length > 0 && (
            <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
              <label className="flex items-center gap-1">Colour <input type="color" value={color} onChange={(e) => setColor(e.target.value)} /></label>
              <label className="flex items-center gap-1"><input type="checkbox" checked={upper} onChange={(e) => setUpper(e.target.checked)} /> UPPERCASE</label>
              <label className="flex items-center gap-1">Animation
                <select className={inp} value={anim} onChange={(e) => setAnim(e.target.value)}><option value="none">none</option><option value="fade">fade</option><option value="pop">pop</option></select></label>
            </div>
          )}

          <div className="flex items-center justify-between"><span className="text-sm font-medium">Music tracks ({d.music.length}/6)</span>
            <button className={btn} disabled={d.music.length >= 6 || tracks.length === 0}
              onClick={() => upd((x) => ({ ...x, music: [...x.music, { uid: nid(), trackId: tracks[0].id, volume: 50, start: 0, trimIn: 0, trimOut: null, fadeIn: 0, fadeOut: 0, loop: false }] }))}><Plus className="inline w-4 h-4" /> Add music</button></div>
          {tracks.length === 0 && <p className="text-xs text-slate-500">No tracks yet. Upload your own in Music Library.</p>}
          {d.music.map((m) => (
            <div key={m.uid} className="rounded-lg border border-slate-700 p-2 space-y-2 text-sm">
              <div className="flex gap-2">
                <select className={inp + " flex-1"} value={m.trackId} onChange={(e) => setMu(m.uid, { trackId: Number(e.target.value) })}>
                  {tracks.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}</select>
                <button className="p-1 text-red-400 hover:bg-slate-700 rounded" onClick={() => upd((x) => ({ ...x, music: x.music.filter((q) => q.uid !== m.uid) }))}><Trash2 className="w-4 h-4" /></button>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <label className={lab}>Volume {m.volume}%<input type="range" min={0} max={100} className="w-28 block" value={m.volume} onChange={(e) => setMu(m.uid, { volume: num(e.target.value, 50) })} /></label>
                <label className={lab}>Start<input type="number" step={0.1} min={0} className={inp + " w-16 block"} value={m.start} onChange={(e) => setMu(m.uid, { start: num(e.target.value) })} /></label>
                <label className={lab}>Trim in<input type="number" step={0.1} min={0} className={inp + " w-16 block"} value={m.trimIn} onChange={(e) => setMu(m.uid, { trimIn: num(e.target.value) })} /></label>
                <label className={lab}>Trim out<input type="number" step={0.1} min={0} className={inp + " w-16 block"} value={m.trimOut ?? ""} placeholder="end" onChange={(e) => setMu(m.uid, { trimOut: e.target.value === "" ? null : num(e.target.value) })} /></label>
                <label className={lab}>Fade in<input type="number" step={0.5} min={0} className={inp + " w-16 block"} value={m.fadeIn} onChange={(e) => setMu(m.uid, { fadeIn: num(e.target.value) })} /></label>
                <label className={lab}>Fade out<input type="number" step={0.5} min={0} className={inp + " w-16 block"} value={m.fadeOut} onChange={(e) => setMu(m.uid, { fadeOut: num(e.target.value) })} /></label>
                <label className="flex items-center gap-1 text-xs text-slate-400"><input type="checkbox" checked={m.loop} onChange={(e) => setMu(m.uid, { loop: e.target.checked })} /> Loop</label>
              </div>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={d.origOn} onChange={(e) => upd((x) => ({ ...x, origOn: e.target.checked }))} /> Keep original audio</label>
            {d.origOn && <label className="flex items-center gap-2 text-xs text-slate-400">Volume {d.origVol}%
              <input type="range" min={0} max={100} value={d.origVol} onChange={(e) => upd((x) => ({ ...x, origVol: num(e.target.value, 100) }))} /></label>}
          </div>
          <p className="text-xs text-slate-500">Music comes only from your own library. Overlays need FFmpeg with libass.</p>
          <button disabled={running || baseId === null || (d.overlays.length === 0 && d.music.length === 0)} onClick={compose}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-5 py-2.5 font-medium">
            {running && kind === "compose" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Film className="w-4 h-4" />} Apply text &amp; music
          </button>
        </div>
      </div>

      {job && running && (
        <div className="rounded-xl border border-slate-700 p-4 space-y-2">
          <div className="h-2 rounded bg-slate-800 overflow-hidden"><div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(job.progress, 100)}%` }} /></div>
          <div className="flex justify-between text-xs text-slate-400">
            <span>{job.status === "queued" ? "Waiting in queue..." : `Working... ${Math.round(job.progress)}%`}</span>
            <button className="text-red-400 hover:underline" onClick={() => { api(`/api/jobs/${job.id}/cancel`, { method: "POST" }).catch(() => null); }}>Cancel</button>
          </div>
        </div>
      )}
      {job && job.status === "completed" && resultId !== null && (
        <div className="rounded-xl border border-emerald-600/50 p-4 space-y-3">
          <h2 className="font-semibold">Result (clip #{resultId}). Saved in Generated Clips.</h2>
          <video key={resultId} controls className="max-h-[480px] rounded-lg bg-black" src={`${API}/api/clips/${resultId}/stream`} />
          <a className="inline-block rounded bg-slate-700 px-3 py-1.5 text-sm" href={`${API}/api/clips/${resultId}/download`}>Download MP4</a>
        </div>
      )}
    </div>
  );
}
