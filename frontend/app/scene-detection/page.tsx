"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Angry, Clapperboard, Compass, Download, Droplets, Eye, Flame, Frown, Ghost, GraduationCap, Heart,
  HeartHandshake, Laugh, Loader2, MessageCircle, Mic, Music, Play, ScanLine, Scissors, Sparkles, Swords,
  Trash2, Users, Wand2, Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { API, fmtClock, watchJob, type VideoItem } from "@/lib/api";

type SceneRow = { idx: number; start_sec: number; end_sec: number };
type CatScene = {
  id: number; category: string; label: string; start_sec: number; end_sec: number; duration_sec: number;
  full_start_sec: number; full_end_sec: number; confidence: number; status: string; source: string;
  description: string; has_thumbnail: boolean; clip_id: number | null; clip_status: string | null;
  verified: boolean | null; filename: string | null;
};
type AiInfo = { warnings?: string[]; gemini_batches?: number; local_units?: number; units?: number } | null;
type Resp = { ok: boolean; data: { detail?: unknown; job_id?: number; created?: number } };

const CATS: { key: string; label: string; Icon: LucideIcon }[] = [
  { key: "fighting", label: "Fighting / Combat Scenes", Icon: Swords },
  { key: "romantic", label: "Romantic Scenes", Icon: Heart },
  { key: "comedy", label: "Comedy / Funny Scenes", Icon: Laugh },
  { key: "emotional", label: "Emotional / Sad Scenes", Icon: Frown },
  { key: "action", label: "Action Scenes", Icon: Zap },
  { key: "horror", label: "Horror / Scary Scenes", Icon: Ghost },
  { key: "suspense", label: "Suspense / Thriller Scenes", Icon: Eye },
  { key: "adventure", label: "Adventure Scenes", Icon: Compass },
  { key: "dramatic", label: "Dramatic Scenes", Icon: Clapperboard },
  { key: "dialogue", label: "Dialogue / Conversation Scenes", Icon: MessageCircle },
  { key: "motivational", label: "Motivational Scenes", Icon: Flame },
  { key: "educational", label: "Educational Scenes", Icon: GraduationCap },
  { key: "dancing", label: "Dancing Scenes", Icon: Music },
  { key: "singing", label: "Singing / Music Scenes", Icon: Mic },
  { key: "crying", label: "Crying Scenes", Icon: Droplets },
  { key: "angry", label: "Angry / Argument Scenes", Icon: Angry },
  { key: "surprise", label: "Surprise / Shocking Scenes", Icon: Sparkles },
  { key: "friendship", label: "Friendship Scenes", Icon: Users },
  { key: "family", label: "Family / Emotional Bonding Scenes", Icon: HeartHandshake },
  { key: "custom", label: "Custom Scene Category", Icon: Wand2 },
];
const DURS: [string, string][] = [
  ["auto", "Complete Scene (Automatic)"], ["30", "30 Seconds"], ["60", "1 Minute"], ["120", "2 Minutes"],
  ["180", "3 Minutes"], ["300", "5 Minutes"], ["600", "10 Minutes"], ["900", "15 Minutes"],
  ["1200", "20 Minutes"], ["custom", "Custom Duration"],
];
const colorOf = (i: number) => `hsl(${(i * 37) % 360} 70% 55%)`;

function hms(sec: number): string {
  const t = Math.max(0, Math.round(sec));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(t / 3600))}:${p(Math.floor((t % 3600) / 60))}:${p(t % 60)}`;
}
async function jreq(path: string, method: string, body?: unknown): Promise<Resp> {
  const r = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, data };
}
const errText = (d: Resp["data"], fb: string) => (typeof d.detail === "string" ? d.detail : fb);

export default function SceneDetectionPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const previewEnd = useRef<number | null>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const stopCutsRef = useRef<(() => void) | null>(null);

  // category selection
  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [dur, setDur] = useState<Record<string, string>>({});
  const [customSec, setCustomSec] = useState<Record<string, number>>({});
  const [customText, setCustomText] = useState("");
  const [previewFirst, setPreviewFirst] = useState(false);
  const [opt, setOpt] = useState({
    min_scene_sec: 10, max_scene_sec: 0, confidence: 60, merge: true, avoid_duplicates: true,
    complete_boundaries: true, subtitles: false, use_vision: true, use_speech: true, mode: "accurate",
  });

  // AI results
  const [aiScenes, setAiScenes] = useState<CatScene[]>([]);
  const [info, setInfo] = useState<AiInfo>(null);
  const [aiProgress, setAiProgress] = useState<number | null>(null);
  const [aiJob, setAiJob] = useState<number | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [showUncertain, setShowUncertain] = useState(true);
  const [edit, setEdit] = useState<{ id: number; start: number; end: number } | null>(null);

  // raw cuts (original feature)
  const [cuts, setCuts] = useState<SceneRow[]>([]);
  const [cutProgress, setCutProgress] = useState<number | null>(null);
  const [minLen, setMinLen] = useState(2);
  const [sent, setSent] = useState<number[]>([]);

  const loadCuts = useCallback(async (id: number) => {
    try {
      const r = await fetch(`${API}/api/analysis/videos/${id}/scenes`);
      if (!r.ok) throw new Error();
      setCuts(((await r.json()) as { items: SceneRow[] }).items);
    } catch { setCuts([]); }
  }, []);

  const loadAi = useCallback(async (id: number) => {
    try {
      const r = await fetch(`${API}/api/scene-ai/videos/${id}/scenes`);
      if (!r.ok) throw new Error();
      const d = (await r.json()) as { items: CatScene[]; info: AiInfo };
      setAiScenes(d.items);
      setInfo(d.info);
    } catch { setAiScenes([]); setInfo(null); }
  }, []);

  useEffect(() => {
    fetch(`${API}/api/videos?limit=500`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d: { items: VideoItem[] }) => {
        const list = d.items.filter((v) => v.has_video);
        setVideos(list);
        if (list.length) setVideoId(list[0].id);
      })
      .catch(() => setMsg("Cannot reach the backend. Start it with .\\scripts\\start-all.ps1"));
    return () => { stopRef.current?.(); stopCutsRef.current?.(); };
  }, []);

  useEffect(() => {
    stopRef.current?.(); stopCutsRef.current?.();
    setAiProgress(null); setCutProgress(null); setMsg(""); setSent([]); setPicked([]); setEdit(null);
    setCuts([]); setAiScenes([]); setInfo(null);
    if (videoId !== null) { loadCuts(videoId); loadAi(videoId); }
  }, [videoId, loadCuts, loadAi]);

  useEffect(() => {
    if (videoId === null) return;
    const need = aiScenes.some((s) => s.clip_status === "pending" || s.clip_status === "processing");
    if (!need) return;
    const t = setInterval(() => loadAi(videoId), 3000);
    return () => clearInterval(t);
  }, [aiScenes, videoId, loadAi]);

  const durationOf = (k: string): string | number => {
    const v = dur[k] ?? "auto";
    if (v === "custom") return customSec[k] ?? 90;
    return v === "auto" ? "auto" : Number(v);
  };

  function watch(jobId: number, id: number) {
    stopRef.current?.();
    setAiJob(jobId); setAiProgress(0);
    stopRef.current = watchJob(jobId, (j) => {
      setAiProgress(j.progress);
      if (["completed", "failed", "cancelled"].includes(j.status)) {
        setAiProgress(null); setAiJob(null);
        if (j.status !== "completed") setMsg(j.error || `Job ${j.status}`);
        loadAi(id);
      }
    });
  }

  async function generate() {
    if (videoId === null) return;
    const categories = CATS.filter((c) => sel[c.key]).map((c) => ({
      key: c.key, custom_text: c.key === "custom" ? customText.trim() : "", duration: durationOf(c.key),
    }));
    if (!categories.length) return setMsg("Select at least one scene category.");
    if (sel.custom && customText.trim().length < 3) return setMsg("Describe your custom scene category.");
    setMsg("");
    const r = await jreq(`/api/scene-ai/videos/${videoId}/run`, "POST", {
      categories, options: { ...opt, auto_extract: !previewFirst },
    });
    if (!r.ok || !r.data.job_id) return setMsg(errText(r.data, "Could not start scene detection."));
    watch(r.data.job_id, videoId);
  }

  async function cancelAi() {
    if (aiJob !== null) await jreq(`/api/jobs/${aiJob}/cancel`, "POST");
  }

  async function extract(ids: number[]) {
    if (videoId === null || !ids.length) return;
    const r = await jreq(`/api/scene-ai/videos/${videoId}/extract`, "POST", { scene_ids: ids, mode: opt.mode, subtitles: opt.subtitles });
    if (!r.ok) return setMsg(errText(r.data, "Could not extract."));
    setMsg(`${r.data.created ?? 0} clip(s) queued. They appear in Generated Clips and below.`);
    setPicked([]);
    loadAi(videoId);
  }

  async function saveEdit() {
    if (!edit || videoId === null) return;
    const r = await jreq(`/api/scene-ai/scenes/${edit.id}`, "PATCH", { start_sec: edit.start, end_sec: edit.end });
    if (!r.ok) return setMsg(errText(r.data, "Could not adjust the scene."));
    setEdit(null);
    loadAi(videoId);
  }

  async function removeScene(id: number) {
    if (videoId === null) return;
    await jreq(`/api/scene-ai/scenes/${id}`, "DELETE");
    loadAi(videoId);
  }

  function preview(start: number, end: number) {
    const v = videoRef.current;
    if (!v) return;
    previewEnd.current = end;
    v.currentTime = start;
    v.play().catch(() => setMsg("This format cannot play in the browser. Use the Manual Clipper preview."));
  }

  // ---- raw cuts ----
  async function detectCuts() {
    if (videoId === null) return;
    const id = videoId;
    const r = await jreq(`/api/analysis/videos/${id}/run`, "POST", { steps: ["scenes"] });
    if (!r.ok || !r.data.job_id) return setMsg(errText(r.data, "Could not start scene detection."));
    setCutProgress(0);
    stopCutsRef.current = watchJob(r.data.job_id, (j) => {
      setCutProgress(j.progress);
      if (["completed", "failed", "cancelled"].includes(j.status)) {
        setCutProgress(null);
        if (j.status !== "completed") setMsg(j.error || `Job ${j.status}`);
        loadCuts(id);
      }
    });
  }
  async function exportCut(s: SceneRow) {
    if (videoId === null) return;
    const r = await jreq("/api/clips", "POST", { video_id: videoId, start_sec: s.start_sec, end_sec: s.end_sec, title: `Scene ${s.idx + 1}`, mode: "accurate" });
    if (r.ok) { setSent((p) => [...p, s.idx]); setMsg(`Scene ${s.idx + 1} queued for export. Check Generated Clips.`); }
    else setMsg(errText(r.data, "Could not create the clip."));
  }

  const vid = videos.find((v) => v.id === videoId);
  const total = vid?.duration_sec ?? (cuts.length ? cuts[cuts.length - 1].end_sec : 0);
  const shown = aiScenes.filter((s) => showUncertain || s.status !== "uncertain");
  const groups = CATS.map((c, i) => ({ c, i, items: shown.filter((s) => s.category === c.key) })).filter((g) => g.items.length);
  const readyIds = shown.filter((s) => !s.clip_id || !["pending", "processing", "ready"].includes(s.clip_status ?? "")).map((s) => s.id);
  const busy = aiProgress !== null;
  const anyExtracted = aiScenes.some((s) => s.clip_status === "ready");
  const numIn = "w-20 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-white";

  return (
    <div className="max-w-6xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
        <ScanLine className="text-violet-400" size={24} /> Scene Detection
      </h1>
      <p className="text-sm text-zinc-400">Choose the kinds of scenes you want. The AI finds them and cuts complete clips into one folder per category.</p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <select value={videoId ?? ""} onChange={(e) => setVideoId(e.target.value ? Number(e.target.value) : null)}
          className="min-w-64 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white">
          {videos.length === 0 && <option value="">No videos uploaded</option>}
          {videos.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
      </div>

      {msg && <p className="mt-4 rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}

      {videoId !== null && (
        <video key={videoId} ref={videoRef} controls className="mt-4 max-h-80 w-full rounded-xl bg-black"
          src={`${API}/api/videos/${videoId}/stream`}
          onTimeUpdate={() => {
            const v = videoRef.current;
            if (v && previewEnd.current !== null && v.currentTime >= previewEnd.current) { v.pause(); previewEnd.current = null; }
          }} />
      )}

      <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="text-lg font-semibold text-white">Select Which Scenes You Want to Extract</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {CATS.map(({ key, label, Icon }, i) => (
            <div key={key} className={`rounded-lg border p-3 ${sel[key] ? "border-violet-500 bg-violet-600/10" : "border-zinc-800"}`}>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-white">
                <input type="checkbox" checked={!!sel[key]} onChange={(e) => setSel((p) => ({ ...p, [key]: e.target.checked }))} />
                <Icon size={16} style={{ color: colorOf(i) }} /> {label}
              </label>
              {sel[key] && (
                <div className="mt-2 space-y-2">
                  {key === "custom" && (
                    <textarea value={customText} onChange={(e) => setCustomText(e.target.value)} rows={2} maxLength={300}
                      placeholder="e.g. Only scenes where two people are fighting"
                      className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-white" />
                  )}
                  <select value={dur[key] ?? "auto"} onChange={(e) => setDur((p) => ({ ...p, [key]: e.target.value }))}
                    className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-white">
                    {DURS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  {dur[key] === "custom" && (
                    <label className="text-xs text-zinc-400">
                      <input type="number" min={5} max={3600} value={customSec[key] ?? 90}
                        onChange={(e) => setCustomSec((p) => ({ ...p, [key]: Number(e.target.value) || 90 }))} className={numIn} /> seconds
                    </label>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        <h3 className="mt-5 text-sm font-semibold text-white">Options</h3>
        <div className="mt-2 grid gap-3 text-sm text-zinc-300 md:grid-cols-2 lg:grid-cols-3">
          <label>Minimum scene (s) <input type="number" min={1} value={opt.min_scene_sec} onChange={(e) => setOpt({ ...opt, min_scene_sec: Number(e.target.value) || 1 })} className={numIn} /></label>
          <label>Maximum scene (s, 0 = none) <input type="number" min={0} value={opt.max_scene_sec} onChange={(e) => setOpt({ ...opt, max_scene_sec: Number(e.target.value) || 0 })} className={numIn} /></label>
          <label>Confidence threshold (%) <input type="number" min={10} max={100} value={opt.confidence} onChange={(e) => setOpt({ ...opt, confidence: Number(e.target.value) || 60 })} className={numIn} /></label>
          {([
            ["merge", "Merge consecutive related scenes"], ["avoid_duplicates", "Avoid duplicate clips"],
            ["complete_boundaries", "Include complete scene boundaries (snap to cuts)"], ["subtitles", "Generate subtitles (.srt next to the clip)"],
            ["use_vision", "Look at video frames (Gemini vision)"], ["use_speech", "Use speech transcript"],
          ] as [keyof typeof opt, string][]).map(([k, l]) => (
            <label key={k} className="flex items-center gap-2">
              <input type="checkbox" checked={opt[k] as boolean} onChange={(e) => setOpt({ ...opt, [k]: e.target.checked })} /> {l}
            </label>
          ))}
          <label className="flex items-center gap-2"><input type="checkbox" checked={previewFirst} onChange={(e) => setPreviewFirst(e.target.checked)} /> Preview before extraction</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked disabled /> Preserve original audio (always on)</label>
          <label>Export mode{" "}
            <select value={opt.mode} onChange={(e) => setOpt({ ...opt, mode: e.target.value })} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-white">
              <option value="accurate">Accurate (exact cut, slower)</option>
              <option value="fast">Fast (copy, may start at a keyframe)</option>
            </select>
          </label>
        </div>
        {opt.use_vision && <p className="mt-2 text-xs text-zinc-500">Vision sends small still frames (about 384 px) of this video to Google Gemini. Turn it off to use the transcript only.</p>}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button onClick={generate} disabled={videoId === null || busy}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Scissors size={16} />}
            {previewFirst ? "Find Scenes" : "Generate Clips"}
          </button>
          {busy && <button onClick={cancelAi} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-orange-300">Cancel</button>}
        </div>
        {busy && (
          <div className="mt-3">
            <div className="h-2 w-full overflow-hidden rounded bg-zinc-800"><div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(aiProgress ?? 0, 100)}%` }} /></div>
            <p className="mt-1 text-xs text-zinc-400">Analyzing... {Math.round(aiProgress ?? 0)}% (long videos take a while, do not restart the backend)</p>
          </div>
        )}
      </section>

      {info?.warnings && info.warnings.length > 0 && (
        <div className="mt-4 rounded-lg border border-amber-700/50 bg-amber-900/20 p-3 text-xs text-amber-200">
          {info.warnings.map((w, i) => <p key={i}>{w}</p>)}
        </div>
      )}

      {aiScenes.length > 0 && (
        <section className="mt-6">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold text-white">Detected Scenes</h2>
            <button onClick={() => setPicked(readyIds)} className="rounded border border-zinc-700 px-3 py-1 text-xs text-zinc-300">Select all detected scenes</button>
            <button onClick={() => extract(picked)} disabled={!picked.length} className="rounded bg-violet-600 px-3 py-1 text-xs text-white disabled:opacity-40">Extract selected ({picked.length})</button>
            {anyExtracted && (
              <a href={`${API}/api/scene-ai/videos/${videoId}/export.zip`} className="inline-flex items-center gap-1 rounded border border-zinc-700 px-3 py-1 text-xs text-zinc-300">
                <Download size={12} /> Export all categories as ZIP
              </a>
            )}
            <label className="text-xs text-zinc-400"><input type="checkbox" checked={showUncertain} onChange={(e) => setShowUncertain(e.target.checked)} /> show uncertain</label>
          </div>

          <div className="mt-3 space-y-1 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            {groups.map(({ c, i, items }) => (
              <div key={c.key} className="flex items-center gap-2 text-xs text-zinc-400">
                <span className="w-40 truncate">{c.label}</span>
                <div className="relative h-4 flex-1 rounded bg-zinc-800">
                  {items.map((s) => (
                    <div key={s.id} title={`${hms(s.start_sec)} - ${hms(s.end_sec)}`} className="absolute h-4 rounded"
                      style={{ left: `${(s.start_sec / (total || 1)) * 100}%`, width: `${Math.max(((s.end_sec - s.start_sec) / (total || 1)) * 100, 0.4)}%`, background: colorOf(i), opacity: s.status === "uncertain" ? 0.45 : 1 }} />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {groups.map(({ c, i, items }) => (
            <div key={c.key} className="mt-5">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-white">
                <c.Icon size={16} style={{ color: colorOf(i) }} /> {c.label}
              </h3>
              <div className="mt-2 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {items.map((s, n) => {
                  const live = s.clip_status === "pending" || s.clip_status === "processing" || s.clip_status === "ready";
                  return (
                    <div key={s.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 text-sm text-zinc-300">
                      {s.has_thumbnail ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={`${API}/api/scene-ai/scenes/${s.id}/thumbnail`} alt="" className="mb-2 w-full rounded" />
                      ) : <div className="mb-2 h-24 rounded bg-zinc-800" />}
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">Scene {String(n + 1).padStart(2, "0")}</span>
                        <label className="text-xs"><input type="checkbox" checked={picked.includes(s.id)} disabled={live}
                          onChange={(e) => setPicked((p) => e.target.checked ? [...p, s.id] : p.filter((x) => x !== s.id))} /> pick</label>
                      </div>
                      <p>Start: {hms(s.start_sec)} | End: {hms(s.end_sec)}</p>
                      <p>Duration: {fmtClock(s.duration_sec)} | Confidence: {Math.round(s.confidence)}%
                        {s.status === "uncertain" && <span className="ml-2 rounded bg-amber-700/40 px-1 text-xs text-amber-200">uncertain</span>}
                        {s.source === "local" && <span className="ml-1 text-xs text-zinc-500">(speech only)</span>}
                      </p>
                      {s.full_end_sec - s.full_start_sec - s.duration_sec > 1 && (
                        <p className="text-xs text-zinc-500">Full scene: {hms(s.full_start_sec)} - {hms(s.full_end_sec)}</p>
                      )}
                      {s.description && <p className="mt-1 text-xs text-zinc-400">{s.description}</p>}
                      {edit?.id === s.id ? (
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                          <input type="number" step={0.5} value={edit.start} onChange={(e) => setEdit({ ...edit, start: Number(e.target.value) })} className={numIn} />
                          <input type="number" step={0.5} value={edit.end} onChange={(e) => setEdit({ ...edit, end: Number(e.target.value) })} className={numIn} />
                          <button onClick={saveEdit} className="rounded bg-violet-600 px-2 py-1 text-white">Save</button>
                          <button onClick={() => setEdit(null)} className="text-zinc-400">Cancel</button>
                        </div>
                      ) : (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <button onClick={() => preview(s.start_sec, s.end_sec)} className="rounded-md bg-zinc-800 p-2 hover:bg-zinc-700" title="Preview"><Play size={14} /></button>
                          {!live && <button onClick={() => extract([s.id])} className="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-1.5 text-xs text-violet-300 hover:bg-zinc-700"><Scissors size={14} /> Extract Clip</button>}
                          {!live && <button onClick={() => setEdit({ id: s.id, start: s.start_sec, end: s.end_sec })} className="text-xs text-zinc-400 underline">Adjust</button>}
                          {!live && <button onClick={() => removeScene(s.id)} className="rounded-md p-2 text-red-400 hover:bg-zinc-800" title="Remove from list"><Trash2 size={14} /></button>}
                        </div>
                      )}
                      {s.clip_status === "ready" && s.clip_id && (
                        <div className="mt-2 text-xs text-green-400">
                          Saved: {s.category}/{s.filename}.mp4 {s.verified === false && <span className="text-amber-300">(length differs from the plan)</span>}
                          <div className="mt-1 flex gap-3"><a className="underline" href={`${API}/api/clips/${s.clip_id}/stream`} target="_blank" rel="noreferrer">Play</a>
                            <a className="underline" href={`${API}/api/clips/${s.clip_id}/download`}>Download</a></div>
                        </div>
                      )}
                      {(s.clip_status === "pending" || s.clip_status === "processing") && <p className="mt-2 text-xs text-yellow-300">Exporting clip...</p>}
                      {s.clip_status === "failed" && <p className="mt-2 text-xs text-red-400">Export failed. Press Extract Clip to retry.</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </section>
      )}

      <details className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-white">Raw scene cuts (technical shot detection)</summary>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button onClick={detectCuts} disabled={videoId === null || cutProgress !== null}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
            {cutProgress !== null ? <Loader2 size={16} className="animate-spin" /> : <ScanLine size={16} />}
            {cuts.length ? "Detect again" : "Detect cuts"}
          </button>
          {cuts.length > 0 && (
            <label className="text-sm text-zinc-400">Hide cuts shorter than{" "}
              <input type="number" min={0} step={0.5} value={minLen} onChange={(e) => setMinLen(Math.max(0, Number(e.target.value) || 0))} className={numIn} /> s
            </label>
          )}
          {cutProgress !== null && <span className="text-xs text-zinc-400">{Math.round(cutProgress)}%</span>}
        </div>
        {cuts.length > 0 && (
          <div className="mt-3 max-h-96 overflow-auto rounded-xl border border-zinc-800">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
                <tr><th className="px-4 py-2">Cut</th><th className="px-4 py-2">Start</th><th className="px-4 py-2">End</th><th className="px-4 py-2">Length</th><th className="px-4 py-2 text-right">Actions</th></tr>
              </thead>
              <tbody>
                {cuts.filter((s) => s.end_sec - s.start_sec >= minLen).map((s) => (
                  <tr key={s.idx} className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/40">
                    <td className="px-4 py-1 text-white">#{s.idx + 1}</td>
                    <td className="px-4 py-1 text-zinc-300">{fmtClock(s.start_sec)}</td>
                    <td className="px-4 py-1 text-zinc-300">{fmtClock(s.end_sec)}</td>
                    <td className="px-4 py-1 text-zinc-300">{(s.end_sec - s.start_sec).toFixed(1)}s</td>
                    <td className="px-4 py-1"><div className="flex justify-end gap-2">
                      <button onClick={() => preview(s.start_sec, s.end_sec)} className="rounded-md bg-zinc-800 p-1.5 hover:bg-zinc-700" title="Play"><Play size={14} /></button>
                      <button onClick={() => exportCut(s)} disabled={sent.includes(s.idx)} className="rounded-md bg-zinc-800 p-1.5 text-violet-300 hover:bg-zinc-700 disabled:opacity-40" title="Export as clip"><Scissors size={14} /></button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>
    </div>
  );
}