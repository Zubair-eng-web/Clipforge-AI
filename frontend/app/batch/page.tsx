"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Layers, Loader2 } from "lucide-react";
import { API, fmtDuration, type VideoItem } from "@/lib/api";

type Row = {
  job_id: number; type: string; video_id: number | null; video_name: string; status: string; progress: number;
  error: string | null; clips_total: number; clips_ready: number; clips_active: number;
  reels_ready: number; reels_failed: number; captions_ready: number; captions_skipped: number; notes: string[]; created_at: string;
};
type Platform = { label: string; ratio: string; max_sec: number };
type Track = { id: number; name: string };

const COLORS: Record<string, string> = {
  completed: "text-emerald-400", failed: "text-red-400", cancelled: "text-zinc-400",
  queued: "text-amber-300", processing: "text-violet-300",
};

export default function BatchPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [count, setCount] = useState(5);
  const [mode, setMode] = useState<"accurate" | "fast">("accurate");
  const [useGemini, setUseGemini] = useState(true);
  const [makeReels, setMakeReels] = useState(false);
  const [platforms, setPlatforms] = useState<Record<string, Platform>>({});
  const [platform, setPlatform] = useState("youtube_shorts");
  const [size, setSize] = useState<"720" | "1080">("720");
  const [reelMode, setReelMode] = useState<"center" | "face" | "blur">("center");
  const [tracks, setTracks] = useState<Track[]>([]);
  const [trackId, setTrackId] = useState("");
  const [musicVol, setMusicVol] = useState(60);
  const [origOn, setOrigOn] = useState(true);
  const [captions, setCaptions] = useState(false);
  const [capPreset, setCapPreset] = useState("gaming");
  const [capLang, setCapLang] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);

  const loadRows = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/batch/jobs?limit=100`);
      if (r.ok) setRows((await r.json()).items as Row[]);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/videos?limit=500`);
        if (!r.ok) throw new Error();
        setVideos(((await r.json()).items as VideoItem[]).filter((v) => v.has_video));
      } catch { setOffline(true); }
    })();
    (async () => {
      try {
        const r = await fetch(`${API}/api/reels-studio/platforms`);
        if (r.ok) setPlatforms((await r.json()).platforms as Record<string, Platform>);
      } catch { /* ignore */ }
    })();
    (async () => {
      try {
        const r = await fetch(`${API}/api/music`);
        if (!r.ok) return;
        const d = await r.json();
        const arr = (Array.isArray(d) ? d : d.items ?? d.tracks ?? []) as Track[];
        setTracks(arr.filter((x) => typeof x.id === "number"));
      } catch { /* ignore */ }
    })();
    loadRows();
  }, [loadRows]);

  useEffect(() => {
    if (!rows.some((r) => r.status === "queued" || r.status === "processing")) return;
    const t = setInterval(loadRows, 2000);
    return () => clearInterval(t);
  }, [rows, loadRows]);

  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const allSelected = videos.length > 0 && selected.length === videos.length;

  async function start() {
    setBusy(true);
    setMsg("");
    try {
      const base = { video_ids: selected, count, mode, use_gemini: useGemini };
      const body = makeReels
        ? {
            ...base, make_reels: true, platform, size, reel_mode: reelMode,
            music: trackId ? [{ track_id: Number(trackId), volume: musicVol / 100 }] : [],
            original_audio_on: origOn, captions, caption_preset: capPreset, caption_language: capLang.trim() || null,
          }
        : captions ? { ...base, captions: true, caption_preset: capPreset, caption_language: capLang.trim() || null } : base;
      const url = makeReels || captions ? `${API}/api/batch/pipeline` : `${API}/api/batch/start`;
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        setMsg(typeof d.detail === "string" ? d.detail : "Could not start the batch. Check the options.");
      } else {
        setMsg(`Queued ${d.created} video(s).${d.skipped_video_ids?.length ? ` Skipped ${d.skipped_video_ids.length} already running.` : ""}`);
        setSelected([]);
        loadRows();
      }
    } catch {
      setMsg("Cannot reach the backend. Is it running?");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(jobId: number) {
    await fetch(`${API}/api/jobs/${jobId}/cancel`, { method: "POST" }).catch(() => null);
    loadRows();
  }

  async function retry(jobId: number) {
    await fetch(`${API}/api/queue/${jobId}/retry`, { method: "POST" }).catch(() => null);
    loadRows();
  }

  async function cancelQueued() {
    await fetch(`${API}/api/queue/cancel-queued`, { method: "POST" }).catch(() => null);
    loadRows();
  }

  return (
    <div className="max-w-5xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Layers size={24} className="text-violet-400" /> Batch Processing</h1>
      <p className="text-sm text-zinc-400">Select several videos. Each one is analyzed (if needed), its best clips are exported, and (optional) a reel with your music is made for every clip. Videos run one after another to protect your RAM.</p>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Videos ({selected.length} selected)</p>
            <button onClick={() => setSelected(allSelected ? [] : videos.map((v) => v.id))} className="text-xs text-violet-400 hover:underline">
              {allSelected ? "Clear" : "Select all"}
            </button>
          </div>
          <div className="max-h-80 space-y-1 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900/60 p-2">
            {videos.length === 0 && <p className="p-3 text-sm text-zinc-500">No videos yet. Upload some first.</p>}
            {videos.map((v) => (
              <label key={v.id} className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-zinc-800">
                <input type="checkbox" checked={selected.includes(v.id)} onChange={() => toggle(v.id)} />
                <span className="flex-1 truncate text-zinc-200">{v.name}</span>
                <span className="text-xs text-zinc-500">{fmtDuration(v.duration_sec)}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <p className="mb-1 text-xs text-zinc-400">Clips per video</p>
            <input type="number" min={1} max={20} value={count}
              onChange={(e) => setCount(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
              className="w-24 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white" />
          </div>
          <select value={mode} onChange={(e) => setMode(e.target.value as "accurate" | "fast")}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white">
            <option value="accurate">Accurate (frame exact)</option>
            <option value="fast">Fast (copy, instant)</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input type="checkbox" checked={useGemini} onChange={(e) => setUseGemini(e.target.checked)} /> Use Gemini for scoring
          </label>

          <label className="flex items-center gap-2 text-sm font-medium text-white">
            <input type="checkbox" checked={makeReels} onChange={(e) => setMakeReels(e.target.checked)} /> Also make a reel for every clip
          </label>
          {makeReels && (
            <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
              <select value={platform} onChange={(e) => setPlatform(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white">
                {Object.entries(platforms).length === 0 && <option value="youtube_shorts">YouTube Shorts</option>}
                {Object.entries(platforms).map(([k, p]) => (
                  <option key={k} value={k}>{p.label} ({p.ratio}, max {p.max_sec}s)</option>
                ))}
              </select>
              <div className="flex gap-2">
                <select value={size} onChange={(e) => setSize(e.target.value as "720" | "1080")}
                  className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-white">
                  <option value="720">720 (light)</option>
                  <option value="1080">1080 (heavy)</option>
                </select>
                <select value={reelMode} onChange={(e) => setReelMode(e.target.value as "center" | "face" | "blur")}
                  className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-white">
                  <option value="center">Center crop</option>
                  <option value="face">Face crop</option>
                  <option value="blur">Blur background</option>
                </select>
              </div>
              <div>
                <p className="mb-1 text-xs text-zinc-400">Music (from your library)</p>
                <select value={trackId} onChange={(e) => setTrackId(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white">
                  <option value="">No music</option>
                  {tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                {trackId && (
                  <div className="mt-2">
                    <p className="text-xs text-zinc-400">Music volume: {musicVol}%</p>
                    <input type="range" min={0} max={100} value={musicVol} onChange={(e) => setMusicVol(Number(e.target.value))} className="w-full" />
                  </div>
                )}
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input type="checkbox" checked={origOn} onChange={(e) => setOrigOn(e.target.checked)} /> Keep original audio
              </label>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm font-medium text-white">
            <input type="checkbox" checked={captions} onChange={(e) => setCaptions(e.target.checked)} /> Add captions to every {makeReels ? "reel" : "clip"}
          </label>
          {captions && (
            <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
              <select value={capPreset} onChange={(e) => setCapPreset(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white">
                <option value="gaming">Gaming</option>
                <option value="viral_reels">Viral Reels</option>
                <option value="cinematic">Cinematic</option>
                <option value="bold_highlight">Bold Highlight</option>
                <option value="minimal">Minimal</option>
                <option value="word_by_word">Word-by-Word</option>
                <option value="karaoke">Karaoke</option>
              </select>
              <input value={capLang} onChange={(e) => setCapLang(e.target.value)} maxLength={10} placeholder="Language code (empty = auto), e.g. en, ur"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white" />
              <p className="text-xs text-zinc-500">Uses Whisper on every clip (slower, needs RAM). Clips without speech stay without captions.</p>
            </div>
          )}
          <button onClick={start} disabled={busy || selected.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Layers size={16} />} Start batch
          </button>
          {msg && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}
        </div>
      </div>

      <div className="mt-8 flex items-center justify-between">
        <h2 className="font-semibold text-white">Batch jobs</h2>
        <div className="flex items-center gap-4">
          <button onClick={cancelQueued} className="text-sm text-red-400 hover:underline">Cancel all waiting</button>
          <Link href="/clips" className="text-sm text-violet-400 hover:underline">Open Generated Clips</Link>
        </div>
      </div>
      <div className="mt-2 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
            <tr><th className="px-4 py-3">Video</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Result</th><th className="px-4 py-3 text-right"> </th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.job_id} className="border-b border-zinc-800/60 last:border-0">
                <td className="max-w-xs px-4 py-3">
                  <div className="truncate text-zinc-200">{r.video_name}</div>
                  <div className="text-[10px] uppercase tracking-wider text-zinc-600">{r.type === "batch_pipeline" ? "clips + reels" : "clips only"}</div>
                  {(r.status === "processing" || r.status === "queued") && (
                    <div className="mt-1 h-1.5 overflow-hidden rounded bg-zinc-800">
                      <div className="h-1.5 bg-violet-500 transition-all" style={{ width: `${Math.min(r.progress, 100)}%` }} />
                    </div>
                  )}
                  {r.error && <div className="mt-1 text-xs text-red-400">{r.error}</div>}
                  {r.status !== "failed" && r.notes?.length > 0 && <div className="mt-1 text-xs text-amber-400">{r.notes[0]}</div>}
                </td>
                <td className={`px-4 py-3 text-xs font-medium ${COLORS[r.status] ?? "text-zinc-400"}`}>
                  {r.status}{r.status === "processing" ? ` ${Math.round(r.progress)}%` : ""}
                </td>
                <td className="px-4 py-3 text-xs text-zinc-400">
                  {r.clips_ready} clips ready{r.clips_active ? `, ${r.clips_active} exporting` : ""}
                  {r.type === "batch_pipeline" && <div>{r.reels_ready} reels ready{r.reels_failed ? `, ${r.reels_failed} failed` : ""}</div>}
                  {r.type === "batch_pipeline" && (r.captions_ready > 0 || r.captions_skipped > 0) && <div>{r.captions_ready} captioned{r.captions_skipped ? `, ${r.captions_skipped} without captions` : ""}</div>}
                </td>
                <td className="px-4 py-3 text-right">
                  {(r.status === "queued" || r.status === "processing") && (
                    <button onClick={() => cancel(r.job_id)} className="text-xs text-red-400 hover:underline">Cancel</button>
                  )}
                  {(r.status === "failed" || r.status === "cancelled") && (
                    <button onClick={() => retry(r.job_id)} className="text-xs text-violet-400 hover:underline">Retry</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="p-6 text-center text-sm text-zinc-500">No batch jobs yet.</p>}
      </div>
    </div>
  );
}