"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Gamepad2, Loader2, Play, Scissors, Trash2 } from "lucide-react";
import { API, api, rows } from "@/lib/api8";

type Vid = { id: number; name: string; duration_sec: number | null; has_video: boolean };
type Cat = { key: string; label: string; hint: string };
type Hi = {
  id: number; category: string; label: string; start_sec: number; end_sec: number; duration_sec: number;
  confidence: number; status: string; source: string; description: string; thumbnail_url: string | null;
  clip_id: number | null; clip_status: string | null; filename: string | null;
};
type Info = { warnings?: string[] } & Record<string, unknown>;

const DURS: [string, string][] = [
  ["auto", "Complete Scene (Automatic)"], ["15", "15 Seconds"], ["30", "30 Seconds"], ["60", "1 Minute"],
  ["120", "2 Minutes"], ["180", "3 Minutes"], ["300", "5 Minutes"],
];

function hms(sec: number): string {
  const t = Math.max(0, Math.round(sec));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(t / 3600))}:${p(Math.floor((t % 3600) / 60))}:${p(t % 60)}`;
}

export default function GamingHighlightsPage() {
  const [videos, setVideos] = useState<Vid[]>([]);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [cats, setCats] = useState<Cat[]>([]);
  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [dur, setDur] = useState<Record<string, string>>({});
  const [customText, setCustomText] = useState("");
  const [confidence, setConfidence] = useState(55);
  const [useVision, setUseVision] = useState(true);
  const [useSpeech, setUseSpeech] = useState(true);
  const [items, setItems] = useState<Hi[]>([]);
  const [info, setInfo] = useState<Info | null>(null);
  const [filter, setFilter] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [msg, setMsg] = useState("");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const stopAt = useRef<number | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadItems = useCallback(async (id: number) => {
    try {
      const d = await api(`/api/gaming/videos/${id}/highlights`);
      setItems((d.items ?? []) as Hi[]);
      setInfo((d.info ?? null) as Info | null);
    } catch { setItems([]); setInfo(null); }
  }, []);

  useEffect(() => {
    api("/api/videos?limit=500")
      .then((d) => {
        const list = (rows(d) as Vid[]).filter((v) => v.has_video);
        setVideos(list);
        if (list.length) setVideoId(list[0].id);
      })
      .catch(() => setMsg("Backend not reachable. Start it with .\\scripts\\start-all.ps1"));
    api("/api/gaming/categories")
      .then((d) => setCats(rows(d) as Cat[]))
      .catch(() => setMsg("Cannot load gaming categories."));
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);

  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    setItems([]); setInfo(null); setPicked([]); setMsg(""); setRunning(false); setProgress(null);
    if (videoId !== null) loadItems(videoId);
  }, [videoId, loadItems]);

  // refresh while clips are being extracted
  useEffect(() => {
    if (videoId === null) return;
    const need = items.some((s) => s.clip_status === "pending" || s.clip_status === "processing");
    if (!need) return;
    const t = setInterval(() => loadItems(videoId), 3000);
    return () => clearInterval(t);
  }, [items, videoId, loadItems]);

  function watch(jobId: number, vid: number) {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const j = await api(`/api/jobs/${jobId}`);
        const st = String(j.status || "");
        if (typeof j.progress === "number") setProgress(j.progress <= 1 ? Math.round(j.progress * 100) : Math.round(j.progress));
        if (st !== "queued" && st !== "processing") {
          if (timer.current) clearInterval(timer.current);
          setRunning(false); setProgress(null);
          if (st === "failed" || st === "error") setMsg("Job failed: " + (j.error || j.message || "see History"));
          else if (st === "cancelled") setMsg("Job cancelled.");
          else setMsg("Done. Highlights updated.");
          loadItems(vid);
        }
      } catch { /* keep polling */ }
    }, 2000);
  }

  async function run() {
    if (videoId === null) return;
    const keys = Object.keys(sel).filter((k) => sel[k]);
    if (!keys.length) { setMsg("Select at least one gaming category."); return; }
    if (keys.includes("custom") && customText.trim().length < 3) { setMsg("Describe the custom category."); return; }
    const categories = keys.map((k) => ({
      key: k, custom_text: k === "custom" ? customText.trim() : "",
      duration: (dur[k] ?? "auto") === "auto" ? "auto" : Number(dur[k]),
    }));
    setMsg(""); setRunning(true); setProgress(0);
    try {
      const d = await api(`/api/gaming/videos/${videoId}/run`, {
        method: "POST",
        body: JSON.stringify({
          categories,
          options: { confidence, use_vision: useVision, use_speech: useSpeech, auto_extract: false },
        }),
      });
      if (d.already_running) setMsg("A gaming job is already running for this video.");
      watch(d.job_id, videoId);
    } catch (e) {
      setRunning(false); setProgress(null); setMsg((e as Error).message);
    }
  }

  async function extract(ids: number[]) {
    if (videoId === null || !ids.length) return;
    setBusy(true); setMsg("");
    try {
      const d = await api(`/api/scene-ai/videos/${videoId}/extract`, {
        method: "POST", body: JSON.stringify({ scene_ids: ids, mode: "accurate", subtitles: false }),
      });
      setMsg(`${d.created} clip(s) queued. They will appear in Generated Clips.`);
      setPicked([]);
      await loadItems(videoId);
    } catch (e) { setMsg((e as Error).message); }
    setBusy(false);
  }

  async function remove(id: number) {
    try {
      await api(`/api/scene-ai/scenes/${id}`, { method: "DELETE" });
      setItems((p) => p.filter((x) => x.id !== id));
    } catch (e) { setMsg((e as Error).message); }
  }

  function preview(h: Hi) {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = h.start_sec;
    stopAt.current = h.end_sec;
    v.play().catch(() => setMsg("This format cannot play in the browser. Use the proxy preview in Manual Clipper."));
    v.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const shown = filter ? items.filter((i) => i.category === filter) : items;
  const usedCats = Array.from(new Set(items.map((i) => i.category)));
  const togglePick = (id: number) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const extractable = shown.filter((s) => !s.clip_id || s.clip_status === "failed");

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div className="flex items-center gap-3">
        <Gamepad2 className="w-7 h-7 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold">AI Gaming Highlights</h1>
          <p className="text-sm text-slate-400">Find fights, chases, crashes, explosions and more in gameplay. Frames + audio + speech are scored together.</p>
        </div>
      </div>

      {msg && <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">{msg}</div>}

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="space-y-3">
          <select className="w-full rounded-lg bg-slate-800 border border-slate-700 p-2"
            value={videoId ?? ""} onChange={(e) => setVideoId(Number(e.target.value))}>
            {videos.length === 0 && <option value="">No videos uploaded</option>}
            {videos.map((v) => <option key={v.id} value={v.id}>{v.name} ({hms(v.duration_sec ?? 0)})</option>)}
          </select>
          <video ref={videoRef} controls className="w-full rounded-lg bg-black max-h-[320px]"
            src={videoId !== null ? `${API}/api/videos/${videoId}/stream` : undefined}
            onTimeUpdate={(e) => {
              if (stopAt.current !== null && e.currentTarget.currentTime >= stopAt.current) {
                e.currentTarget.pause(); stopAt.current = null;
              }
            }} />
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Select gaming categories</h2>
            <div className="text-xs space-x-3">
              <button className="underline" onClick={() => setSel(Object.fromEntries(cats.filter((c) => c.key !== "custom").map((c) => [c.key, true])))}>All</button>
              <button className="underline" onClick={() => setSel({})}>None</button>
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-2 max-h-[300px] overflow-y-auto pr-1">
            {cats.map((c) => (
              <div key={c.key} className={`rounded-lg border p-2 text-sm ${sel[c.key] ? "border-violet-500 bg-violet-500/10" : "border-slate-700"}`}>
                <label className="flex items-center gap-2 cursor-pointer" title={c.hint}>
                  <input type="checkbox" checked={!!sel[c.key]} onChange={(e) => setSel({ ...sel, [c.key]: e.target.checked })} />
                  <span>{c.label}</span>
                </label>
                {sel[c.key] && (
                  <select className="mt-1 w-full text-xs rounded bg-slate-800 border border-slate-700 p-1"
                    value={dur[c.key] ?? "auto"} onChange={(e) => setDur({ ...dur, [c.key]: e.target.value })}>
                    {DURS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                )}
              </div>
            ))}
          </div>
          {sel["custom"] && (
            <input className="w-full rounded-lg bg-slate-800 border border-slate-700 p-2 text-sm"
              placeholder="Describe your category (e.g. helicopter landing)" value={customText}
              onChange={(e) => setCustomText(e.target.value)} />
          )}
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-2">Min confidence
              <input type="number" min={10} max={100} value={confidence} className="w-16 rounded bg-slate-800 border border-slate-700 p-1"
                onChange={(e) => setConfidence(Number(e.target.value))} />
            </label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={useVision} onChange={(e) => setUseVision(e.target.checked)} /> Look at video frames</label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={useSpeech} onChange={(e) => setUseSpeech(e.target.checked)} /> Use speech</label>
          </div>
          {useVision && <p className="text-xs text-amber-400">Privacy: small still frames are sent to Google Gemini. Turn off to use audio and speech only (scenes will be &quot;uncertain&quot;).</p>}
          <button disabled={running || videoId === null} onClick={run}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-4 py-2 font-medium">
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Gamepad2 className="w-4 h-4" />}
            {running ? `Analyzing${progress !== null ? " " + progress + "%" : "..."}` : "Find Gaming Highlights"}
          </button>
        </div>
      </div>

      {info?.warnings && info.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-600/50 bg-amber-500/10 p-3 text-sm space-y-1">
          {info.warnings.map((w, i) => <div key={i}>{w}</div>)}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-semibold">Highlights ({shown.length})</h2>
        <select className="rounded bg-slate-800 border border-slate-700 p-1 text-sm" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All categories</option>
          {usedCats.map((k) => <option key={k} value={k}>{items.find((i) => i.category === k)?.label ?? k}</option>)}
        </select>
        <button className="text-xs underline" onClick={() => setPicked(extractable.map((s) => s.id))}>Select all</button>
        <button className="text-xs underline" onClick={() => setPicked([])}>Clear</button>
        <button disabled={!picked.length || busy} onClick={() => extract(picked)}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-3 py-1.5 text-sm">
          <Scissors className="w-4 h-4" /> Extract selected ({picked.length})
        </button>
      </div>

      {shown.length === 0 && <p className="text-sm text-slate-400">No highlights yet. Pick categories and press &quot;Find Gaming Highlights&quot;.</p>}

      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {shown.map((h) => {
          const done = h.clip_status === "ready";
          const working = h.clip_status === "pending" || h.clip_status === "processing";
          return (
            <div key={h.id} className={`rounded-xl border overflow-hidden ${picked.includes(h.id) ? "border-emerald-500" : "border-slate-700"} bg-slate-900`}>
              <div className="relative aspect-video bg-black">
                {h.thumbnail_url
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={`${API}${h.thumbnail_url}`} alt={h.label} className="w-full h-full object-cover" />
                  : <div className="w-full h-full grid place-items-center text-slate-600 text-sm">No thumbnail</div>}
                <span className="absolute top-2 left-2 rounded bg-black/70 px-2 py-0.5 text-xs">{h.label}</span>
                <span className={`absolute top-2 right-2 rounded px-2 py-0.5 text-xs ${h.status === "detected" ? "bg-emerald-600" : "bg-amber-600"}`}>
                  {h.status === "detected" ? "Detected" : "Uncertain"} {Math.round(h.confidence)}%
                </span>
              </div>
              <div className="p-3 space-y-2 text-sm">
                <div className="text-slate-300">{hms(h.start_sec)} - {hms(h.end_sec)} <span className="text-slate-500">({Math.round(h.duration_sec)}s)</span></div>
                <p className="text-slate-400 text-xs line-clamp-3">{h.description || "No description"}</p>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => preview(h)} className="inline-flex items-center gap-1 rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-xs"><Play className="w-3 h-3" /> Preview</button>
                  {done ? (
                    <a href={`/clips`} className="inline-flex items-center gap-1 rounded bg-emerald-700 px-2 py-1 text-xs"><Check className="w-3 h-3" /> Extracted</a>
                  ) : working ? (
                    <span className="inline-flex items-center gap-1 text-xs text-slate-400"><Loader2 className="w-3 h-3 animate-spin" /> Extracting</span>
                  ) : (
                    <>
                      <button disabled={busy} onClick={() => extract([h.id])} className="inline-flex items-center gap-1 rounded bg-violet-700 hover:bg-violet-600 px-2 py-1 text-xs"><Scissors className="w-3 h-3" /> Extract Clip</button>
                      <label className="inline-flex items-center gap-1 text-xs"><input type="checkbox" checked={picked.includes(h.id)} onChange={() => togglePick(h.id)} /> Select</label>
                    </>
                  )}
                  <button onClick={() => remove(h.id)} className="ml-auto text-slate-500 hover:text-red-400" title="Remove highlight (clip stays)"><Trash2 className="w-4 h-4" /></button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}