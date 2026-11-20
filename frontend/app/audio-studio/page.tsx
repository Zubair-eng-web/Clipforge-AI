"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Headphones, Loader2, RotateCcw, Sparkles, X } from "lucide-react";
import Wave from "@/components/Wave";
import { API, watchJob, type ClipItem, type JobItem } from "@/lib/api";
import { api } from "@/lib/api8";

type Cfg = { uid: number; track_id: number; volume: number; start: number; trim_in: number; trim_out: string; fade_in: number; fade_out: number; loop: boolean; enabled: boolean };
const COLORS = ["#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#60a5fa", "#fb923c"];
const CATS = ["", "fighting", "action", "romantic", "comedy", "horror", "suspense", "emotional", "crying", "dramatic", "adventure", "motivational", "dancing", "friendship", "family", "angry", "surprise"];
const num = (v: string, d = 0) => (v !== "" && Number.isFinite(Number(v)) ? Number(v) : d);

export default function AudioStudioPage() {
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [lib, setLib] = useState<any[]>([]);
  const [peaks, setPeaks] = useState<Record<number, number[]>>({});
  const [origOn, setOrigOn] = useState(true);
  const [origVol, setOrigVol] = useState(100);
  const [cfgs, setCfgs] = useState<Cfg[]>([]);
  const [codec, setCodec] = useState("aac");
  const [bitrate, setBitrate] = useState(192);
  const [category, setCategory] = useState("");
  const [sugg, setSugg] = useState<any>(null);
  const [job, setJob] = useState<JobItem | null>(null);
  const [kind, setKind] = useState<"mix" | "preview">("mix");
  const [previewUrl, setPreviewUrl] = useState("");
  const [resultId, setResultId] = useState<number | null>(null);
  const [pick, setPick] = useState("");
  const [err, setErr] = useState("");
  const uid = useRef(1);
  const stopRef = useRef<(() => void) | null>(null);
  const firstTrack = useRef<number>(0);

  const clip = clips.find((c) => c.id === clipId) ?? null;
  const dur = clip?.duration_sec ?? 0;
  const libMap: Record<number, any> = {};
  lib.forEach((m) => { libMap[m.id] = m; });
  const running = job !== null && (job.status === "queued" || job.status === "processing");

  const loadPeaks = useCallback((id: number) => {
    api(`/api/music/${id}/waveform`).then((d) => setPeaks((p) => ({ ...p, [id]: d.peaks }))).catch(() => undefined);
  }, []);

  const addTrack = useCallback((id: number) => {
    setCfgs((p) => [...p, { uid: uid.current++, track_id: id, volume: 50, start: 0, trim_in: 0, trim_out: "", fade_in: 0, fade_out: 0, loop: false, enabled: true }]);
    loadPeaks(id);
  }, [loadPeaks]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const c = Number(q.get("clip"));
    firstTrack.current = Number(q.get("track")) || 0;
    setCategory(q.get("category") || "");
    (async () => {
      try {
        const d = await (await fetch(`${API}/api/clips?limit=300`)).json();
        const ready = (d.items as ClipItem[]).filter((x) => x.status === "ready" && x.has_file);
        setClips(ready);
        setClipId(ready.some((x) => x.id === c) ? c : ready[0]?.id ?? null);
        const l = await api("/api/music?limit=500");
        setLib(l.items);
        if (firstTrack.current && l.items.some((m: any) => m.id === firstTrack.current)) addTrack(firstTrack.current);
      } catch { setErr("Cannot reach the backend. Is it running?"); }
    })();
    return () => stopRef.current?.();
  }, [addTrack]);

  const upd = (u: number, patch: Partial<Cfg>) => setCfgs((p) => p.map((c) => (c.uid === u ? { ...c, ...patch } : c)));
  function reset() { setOrigOn(true); setOrigVol(100); setCfgs([]); setCodec("aac"); setBitrate(192); setSugg(null); setPreviewUrl(""); setResultId(null); setJob(null); setErr(""); }

  const playLen = (c: Cfg) => {
    const td = libMap[c.track_id]?.duration_sec ?? 0;
    const avail = Math.max(dur - c.start, 0);
    if (c.loop) return avail;
    const to = c.trim_out !== "" ? Math.min(num(c.trim_out), td) : td;
    return Math.max(Math.min(avail, to - c.trim_in), 0);
  };

  function body() {
    return {
      original_enabled: origOn, original_volume: origVol, codec, bitrate_kbps: bitrate,
      tracks: cfgs.map((c) => ({ track_id: c.track_id, volume: c.volume, start_sec: c.start, trim_in: c.trim_in,
        trim_out: c.trim_out === "" ? null : num(c.trim_out), fade_in: c.fade_in, fade_out: c.fade_out, loop: c.loop, enabled: c.enabled })),
    };
  }

  async function run(k: "mix" | "preview") {
    if (clipId === null) return;
    setErr(""); setResultId(null); setPreviewUrl(""); setKind(k);
    try {
      const d = await api(`/api/audio-studio/clips/${clipId}/${k}${k === "preview" ? "?seconds=20" : ""}`, { method: "POST", body: JSON.stringify(body()) });
      setJob({ id: d.job_id, type: "", video_id: null, status: "queued", progress: 0, error: null, created_at: "", updated_at: "" });
      stopRef.current?.();
      stopRef.current = watchJob(d.job_id, (j) => {
        setJob(j);
        if (j.status === "completed") {
          if (k === "preview") setPreviewUrl(`${API}/api/audio-studio/preview/${d.job_id}?t=${Date.now()}`);
          else setResultId(d.clip_id);
        }
      });
    } catch (e: any) {
      setErr(typeof e.message === "string" ? e.message : "Request failed");
    }
  }
  async function cancel() { if (job) await fetch(`${API}/api/jobs/${job.id}/cancel`, { method: "POST" }).catch(() => null); }

  async function suggest() {
    setErr("");
    try { setSugg(await api("/api/audio-studio/suggest", { method: "POST", body: JSON.stringify({ clip_id: clipId, category }) })); }
    catch (e: any) { setErr(e.message); }
  }

  const inp = "w-20 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-white";
  const sel = "rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-white";

  return (
    <div className="max-w-6xl space-y-5 text-zinc-200">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Headphones className="text-violet-400" size={24} /> Audio Studio</h1>
      <p className="text-sm text-zinc-400">Mix your own music into a clip. The picture is never re-encoded: resolution, frame rate, cuts and length stay the same. The result is a new clip; the original is untouched.</p>
      {err && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-red-400">{err}</p>}
      {clips.length === 0 && !err && <p className="text-zinc-500">No ready clips yet. Create a clip first.</p>}

      {clip && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <select value={clipId ?? ""} onChange={(e) => { setClipId(Number(e.target.value)); setCfgs((p) => p); setPreviewUrl(""); setResultId(null); }} className={sel + " min-w-64"}>
              {clips.map((c) => <option key={c.id} value={c.id}>{c.title} ({c.duration_sec.toFixed(1)}s)</option>)}
            </select>
            <button onClick={reset} className="inline-flex items-center gap-1 rounded bg-zinc-800 px-3 py-1.5 text-sm hover:bg-zinc-700"><RotateCcw size={14} /> Reset audio settings</button>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div>
              <video key={clip.id} controls className="max-h-72 w-full rounded-xl bg-black" src={`${API}/api/clips/${clip.id}/stream`} />
              <p className="mt-1 text-xs text-zinc-500">This shows the clip with its original sound. Use Preview below to hear your mix.</p>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Timeline (0 - {dur.toFixed(1)} s)</p>
              <div className="space-y-2 text-xs">
                <div className="flex items-center gap-2"><span className="w-24 text-zinc-400">Video</span>
                  <div className="relative h-8 flex-1 rounded bg-zinc-800"><div className="absolute inset-0 truncate rounded bg-sky-700/60 px-2 leading-8 text-white">{clip.title} (copied, not re-encoded)</div></div></div>
                <div className="flex items-center gap-2"><span className="w-24 text-zinc-400">Original audio</span>
                  <div className="relative h-8 flex-1 rounded bg-zinc-800"><div className="absolute inset-0 rounded bg-emerald-700/50 px-2 leading-8 text-white" style={{ opacity: origOn ? Math.max(origVol / 100, 0.15) : 0.12 }}>{origOn ? `${origVol}%` : "OFF"}</div></div></div>
                {cfgs.map((c, i) => {
                  const m = libMap[c.track_id];
                  const td = m?.duration_sec ?? 1;
                  const len = playLen(c);
                  return (
                    <div key={c.uid} className="flex items-center gap-2"><span className="w-24 truncate text-zinc-400" title={m?.name}>Music {i + 1}</span>
                      <div className="relative h-10 flex-1 rounded bg-zinc-800">
                        {dur > 0 && len > 0 && (
                          <div className="absolute top-0 h-10 overflow-hidden rounded border border-white/10" style={{ left: `${(c.start / dur) * 100}%`, width: `${(len / dur) * 100}%`, background: COLORS[i % 6] + "33", opacity: c.enabled ? 1 : 0.3 }}>
                            {peaks[c.track_id] ? <Wave peaks={peaks[c.track_id]} from={c.trim_in / td} to={(c.trim_out !== "" ? num(c.trim_out) : td) / td} color={COLORS[i % 6]} /> : null}
                          </div>
                        )}
                      </div></div>
                  );
                })}
              </div>
            </div>
          </div>

          <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <h2 className="font-semibold text-white">Original audio</h2>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={origOn} onChange={(e) => setOrigOn(e.target.checked)} /> Keep original audio (voices, sound effects)</label>
              <label className="flex items-center gap-2">Volume <input type="range" min={0} max={100} value={origVol} disabled={!origOn} onChange={(e) => setOrigVol(Number(e.target.value))} /> {origVol}%</label>
            </div>
          </section>

          <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="font-semibold text-white">Music tracks ({cfgs.length}/6)</h2>
              <select value={pick} onChange={(e) => { if (e.target.value) { addTrack(Number(e.target.value)); } setPick(""); }} className={sel} disabled={cfgs.length >= 6}>
                <option value="">+ Add track from library...</option>
                {lib.map((m) => <option key={m.id} value={m.id}>{m.name} ({(m.duration_sec ?? 0).toFixed(0)}s)</option>)}
              </select>
              {lib.length === 0 && <a href="/music" className="text-xs text-violet-300 underline">Library is empty: upload music</a>}
              <select value={category} onChange={(e) => setCategory(e.target.value)} className={sel}>
                {CATS.map((c) => <option key={c} value={c}>{c ? c : "Scene type (auto)"}</option>)}
              </select>
              <button onClick={suggest} className="inline-flex items-center gap-1 rounded bg-zinc-800 px-3 py-1.5 text-sm text-violet-300 hover:bg-zinc-700"><Sparkles size={14} /> Suggest from my library</button>
            </div>

            {sugg && (
              <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm">
                <p className="text-xs text-zinc-500">Suggestions for <b>{sugg.category}</b> ({sugg.source === "gemini" ? "AI, from track names and tags" : "name/tag match"}). Nothing is applied until you approve it.</p>
                {sugg.message && <p className="mt-1 text-amber-300">{sugg.message}</p>}
                {sugg.items.map((s: any) => (
                  <div key={s.track_id} className="mt-1 flex items-center justify-between gap-2">
                    <span>{s.name} <span className="text-xs text-zinc-500">({s.score}%) {s.reason}</span></span>
                    <button onClick={() => addTrack(s.track_id)} className="rounded bg-violet-600 px-2 py-1 text-xs text-white">Approve and add</button>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-3 space-y-3">
              {cfgs.map((c, i) => (
                <div key={c.uid} className="rounded-lg border border-zinc-800 p-3 text-sm" style={{ borderLeft: `4px solid ${COLORS[i % 6]}` }}>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white">Music {i + 1}: {libMap[c.track_id]?.name ?? "deleted track"}</span>
                    <button onClick={() => setCfgs((p) => p.filter((x) => x.uid !== c.uid))} className="text-red-400" title="Remove"><X size={16} /></button>
                  </div>
                  <audio controls preload="none" className="mt-1 h-8 w-full" src={`${API}/api/music/${c.track_id}/stream`} />
                  <div className="mt-2 grid gap-3 md:grid-cols-3">
                    <label className="flex items-center gap-2"><input type="checkbox" checked={c.enabled} onChange={(e) => upd(c.uid, { enabled: e.target.checked })} /> Enabled</label>
                    <label className="flex items-center gap-2 md:col-span-2">Volume <input type="range" min={0} max={100} value={c.volume} onChange={(e) => upd(c.uid, { volume: Number(e.target.value) })} /> {c.volume}%</label>
                    <label>Start in clip (s) <input type="number" min={0} step={0.5} value={c.start} onChange={(e) => upd(c.uid, { start: Math.max(0, Number(e.target.value) || 0) })} className={inp} /></label>
                    <label>Music from (s) <input type="number" min={0} step={0.5} value={c.trim_in} onChange={(e) => upd(c.uid, { trim_in: Math.max(0, Number(e.target.value) || 0) })} className={inp} /></label>
                    <label>Music to (s, empty = end) <input value={c.trim_out} onChange={(e) => upd(c.uid, { trim_out: e.target.value })} className={inp} /></label>
                    <label>Fade in (s) <input type="number" min={0} max={30} step={0.5} value={c.fade_in} onChange={(e) => upd(c.uid, { fade_in: Math.max(0, Number(e.target.value) || 0) })} className={inp} /></label>
                    <label>Fade out (s) <input type="number" min={0} max={30} step={0.5} value={c.fade_out} onChange={(e) => upd(c.uid, { fade_out: Math.max(0, Number(e.target.value) || 0) })} className={inp} /></label>
                    <label className="flex items-center gap-2"><input type="checkbox" checked={c.loop} onChange={(e) => upd(c.uid, { loop: e.target.checked })} /> Loop if shorter than the clip</label>
                  </div>
                </div>
              ))}
              {cfgs.length === 0 && <p className="text-zinc-500">No music added yet.</p>}
            </div>
          </section>

          <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <label>Audio codec{" "}
                <select value={codec} onChange={(e) => setCodec(e.target.value)} className={sel}><option value="aac">AAC (best compatibility)</option><option value="mp3">MP3</option><option value="opus">Opus</option></select></label>
              <label>Quality{" "}
                <select value={bitrate} onChange={(e) => setBitrate(Number(e.target.value))} className={sel}>{[96, 128, 160, 192, 256, 320].map((b) => <option key={b} value={b}>{b} kbps</option>)}</select></label>
              <button onClick={() => run("preview")} disabled={running || cfgs.length === 0} className="rounded bg-zinc-800 px-4 py-2 hover:bg-zinc-700 disabled:opacity-40">Preview (first 20 s)</button>
              <button onClick={() => run("mix")} disabled={running || cfgs.length === 0} className="inline-flex items-center gap-2 rounded bg-violet-600 px-4 py-2 font-medium text-white hover:bg-violet-500 disabled:opacity-40">
                {running && kind === "mix" ? <Loader2 size={16} className="animate-spin" /> : null} Export MP4
              </button>
            </div>
            {job && running && (
              <div className="mt-3">
                <div className="h-2 overflow-hidden rounded bg-zinc-800"><div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(job.progress, 100)}%` }} /></div>
                <div className="mt-1 flex justify-between text-xs text-zinc-400"><span>{job.status === "queued" ? "Waiting in queue..." : `Working... ${Math.round(job.progress)}%`}</span><button onClick={cancel} className="text-red-400">Cancel</button></div>
              </div>
            )}
            {job && job.status === "failed" && <p className="mt-3 text-sm text-red-400">Failed: {job.error}</p>}
            {job && job.status === "cancelled" && <p className="mt-3 text-sm text-amber-300">Cancelled.</p>}
            {previewUrl && (<div className="mt-3"><p className="text-xs text-zinc-500">Preview (not saved as a clip)</p><video key={previewUrl} controls autoPlay className="max-h-72 rounded bg-black" src={previewUrl} /></div>)}
            {resultId !== null && job?.status === "completed" && (
              <div className="mt-3">
                <p className="text-xs text-green-400">Saved as a new clip in Generated Clips (storage/edited_clips).</p>
                <video key={resultId} controls className="mt-1 max-h-72 rounded bg-black" src={`${API}/api/clips/${resultId}/stream`} />
                <a href={`${API}/api/clips/${resultId}/download`} className="mt-2 inline-flex items-center gap-2 rounded bg-zinc-800 px-3 py-2 text-sm hover:bg-zinc-700"><Download size={15} /> Download</a>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}