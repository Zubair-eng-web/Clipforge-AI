"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Loader2, Smartphone } from "lucide-react";
import { API, api, rows } from "@/lib/api8";

type ClipRow = { id: number; title: string; status: string; duration_sec: number | null };
type Platform = { label: string; ratio: string; max_sec: number };
type Meta = { platforms: Record<string, Platform>; durations: number[]; modes: string[] };
type Track = { id: number; name: string; duration_sec: number | null };

const inp = "rounded bg-slate-800 border border-slate-700 p-2 text-sm";

export default function ReelsStudioPage() {
  const [clips, setClips] = useState<ClipRow[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [platform, setPlatform] = useState("youtube_shorts");
  const [size, setSize] = useState("1080");
  const [mode, setMode] = useState("face");
  const [cx, setCx] = useState(0.5);
  const [cy, setCy] = useState(0.5);
  const [target, setTarget] = useState("");
  const [trimDead, setTrimDead] = useState(true);
  const [brightness, setBrightness] = useState(0);
  const [contrast, setContrast] = useState(1);
  const [saturation, setSaturation] = useState(1);
  const [origOn, setOrigOn] = useState(true);
  const [origVol, setOrigVol] = useState(1);
  const [music, setMusic] = useState<Record<number, number>>({});
  const [title, setTitle] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api("/api/clips?limit=500")
      .then((d) => {
        const list = (rows(d) as ClipRow[]).filter((c) => c.status === "ready");
        setClips(list);
        if (list.length) setClipId(list[0].id);
      })
      .catch(() => setMsg("Backend not reachable. Start it with .\\scripts\\start-all.ps1"));
    api("/api/reels-studio/platforms").then((d) => setMeta(d as Meta)).catch(() => setMsg("Cannot load platforms."));
    api("/api/music").then((d) => setTracks(rows(d) as Track[])).catch(() => setTracks([]));
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);

  const plat = meta?.platforms[platform];
  const durations = (meta?.durations ?? []).filter((s) => !plat || s <= plat.max_sec);

  function watch(jobId: number, newClip: number) {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const j = await api(`/api/jobs/${jobId}`);
        const st = String(j.status || "");
        if (typeof j.progress === "number") setProgress(j.progress <= 1 ? Math.round(j.progress * 100) : Math.round(j.progress));
        if (st !== "queued" && st !== "processing") {
          if (timer.current) clearInterval(timer.current);
          setBusy(false); setProgress(null);
          if (st === "failed" || st === "error") setMsg("Reel failed: " + (j.error || j.message || "see History"));
          else if (st === "cancelled") setMsg("Cancelled.");
          else { setResult(newClip); setMsg("Reel ready. Original clip is untouched."); }
        }
      } catch { /* keep polling */ }
    }, 2000);
  }

  async function create() {
    if (clipId === null) return;
    setBusy(true); setMsg(""); setResult(null); setProgress(0);
    const body: Record<string, unknown> = {
      clip_id: clipId, platform, size, mode, trim_dead_time: trimDead, brightness, contrast, saturation,
      original_audio_on: origOn, original_volume: origVol, title: title.trim(),
      music: Object.entries(music).map(([id, vol]) => ({ track_id: Number(id), volume: vol })),
    };
    if (mode === "manual") { body.cx = cx; body.cy = cy; }
    if (target) body.target_sec = Number(target);
    try {
      const d = await api("/api/reels-studio/create", { method: "POST", body: JSON.stringify(body) });
      watch(d.job_id as number, d.clip_id as number);
    } catch (e) {
      setBusy(false); setProgress(null); setMsg((e as Error).message);
    }
  }

  const toggleTrack = (id: number) =>
    setMusic((m) => { const n = { ...m }; if (id in n) delete n[id]; else n[id] = 0.6; return n; });

  return (
    <div className="p-6 space-y-5 max-w-6xl text-slate-200">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Smartphone className="w-7 h-7 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold">Reels &amp; Shorts Studio</h1>
            <p className="text-sm text-slate-400">Turn a clip into a vertical reel: reframe, trim dead time, optional music from your library.</p>
          </div>
        </div>
        <Link href="/reels-library" className="rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Reels Library</Link>
      </div>

      {msg && <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">{msg}</div>}

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="space-y-3">
          <label className="block text-sm">Clip
            <select className={inp + " w-full mt-1"} value={clipId ?? ""} onChange={(e) => { setClipId(Number(e.target.value)); setResult(null); }}>
              {clips.length === 0 && <option value="">No ready clips (make one in Manual Clipper or Gaming Highlights)</option>}
              {clips.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.title} {c.duration_sec ? `(${Math.round(c.duration_sec)}s)` : ""}</option>)}
            </select>
          </label>
          {clipId !== null && (
            <video key={clipId} controls className="w-full rounded-lg bg-black max-h-[300px]" src={`${API}/api/clips/${clipId}/stream`} />
          )}
          <label className="block text-sm">Title (optional)
            <input className={inp + " w-full mt-1"} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          </label>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">Platform
              <select className={inp + " w-full mt-1"} value={platform} onChange={(e) => { setPlatform(e.target.value); setTarget(""); }}>
                {meta && Object.entries(meta.platforms).map(([k, p]) => <option key={k} value={k}>{p.label} ({p.ratio})</option>)}
              </select>
            </label>
            <label className="text-sm">Size
              <select className={inp + " w-full mt-1"} value={size} onChange={(e) => setSize(e.target.value)}>
                <option value="1080">1080p (slower)</option>
                <option value="720">720p (faster, good for 8GB RAM)</option>
              </select>
            </label>
            <label className="text-sm">Length
              <select className={inp + " w-full mt-1"} value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Keep full clip</option>
                {durations.map((s) => <option key={s} value={s}>{s} seconds</option>)}
              </select>
            </label>
            <label className="text-sm">Reframe
              <select className={inp + " w-full mt-1"} value={mode} onChange={(e) => setMode(e.target.value)}>
                {(meta?.modes ?? ["face", "center", "blur", "manual"]).map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          </div>
          {plat && <p className="text-xs text-slate-500">{plat.label}: max {plat.max_sec}s. Longer targets are refused.</p>}
          {mode === "manual" && (
            <div className="grid grid-cols-2 gap-3 text-sm">
              <label>Horizontal {cx.toFixed(2)}<input type="range" min={0} max={1} step={0.01} value={cx} onChange={(e) => setCx(Number(e.target.value))} className="w-full" /></label>
              <label>Vertical {cy.toFixed(2)}<input type="range" min={0} max={1} step={0.01} value={cy} onChange={(e) => setCy(Number(e.target.value))} className="w-full" /></label>
            </div>
          )}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={trimDead} onChange={(e) => setTrimDead(e.target.checked)} /> Trim silent dead time at start/end</label>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <label>Brightness {brightness.toFixed(2)}<input type="range" min={-0.5} max={0.5} step={0.05} value={brightness} onChange={(e) => setBrightness(Number(e.target.value))} className="w-full" /></label>
            <label>Contrast {contrast.toFixed(2)}<input type="range" min={0.5} max={1.5} step={0.05} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} className="w-full" /></label>
            <label>Saturation {saturation.toFixed(2)}<input type="range" min={0} max={2} step={0.05} value={saturation} onChange={(e) => setSaturation(Number(e.target.value))} className="w-full" /></label>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700 p-4 space-y-3">
        <h2 className="font-semibold">Audio</h2>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={origOn} onChange={(e) => setOrigOn(e.target.checked)} /> Keep original audio</label>
          {origOn && <label className="flex items-center gap-2">Volume {Math.round(origVol * 100)}%<input type="range" min={0} max={1} step={0.05} value={origVol} onChange={(e) => setOrigVol(Number(e.target.value))} /></label>}
        </div>
        <p className="text-xs text-slate-500">Music comes only from your own Music Library. Copyright of your files is your responsibility.</p>
        {tracks.length === 0 && <p className="text-sm text-slate-400">No tracks yet. <Link href="/music" className="underline">Add music</Link></p>}
        <div className="grid sm:grid-cols-2 gap-2 max-h-[220px] overflow-y-auto">
          {tracks.map((t) => (
            <div key={t.id} className={`rounded-lg border p-2 text-sm ${t.id in music ? "border-violet-500 bg-violet-500/10" : "border-slate-700"}`}>
              <label className="flex items-center gap-2"><input type="checkbox" checked={t.id in music} onChange={() => toggleTrack(t.id)} /> <span className="truncate">{t.name}</span></label>
              {t.id in music && (
                <label className="flex items-center gap-2 text-xs mt-1">Volume {Math.round(music[t.id] * 100)}%
                  <input type="range" min={0} max={1} step={0.05} value={music[t.id]} onChange={(e) => setMusic({ ...music, [t.id]: Number(e.target.value) })} />
                </label>
              )}
            </div>
          ))}
        </div>
      </div>

      <button disabled={busy || clipId === null} onClick={create}
        className="inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-5 py-2.5 font-medium">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Smartphone className="w-4 h-4" />}
        {busy ? `Creating${progress !== null ? " " + progress + "%" : "..."}` : "Create Reel"}
      </button>

      {result !== null && (
        <div className="rounded-xl border border-emerald-600/50 p-4 space-y-3">
          <h2 className="font-semibold">Your reel (clip #{result})</h2>
          <video controls className="max-h-[480px] rounded-lg bg-black" src={`${API}/api/clips/${result}/stream`} />
          <div className="flex flex-wrap gap-3 text-sm">
            <a className="rounded bg-slate-700 px-3 py-1.5" href={`${API}/api/clips/${result}/download`}>Download MP4</a>
            <Link className="rounded bg-slate-700 px-3 py-1.5" href="/captions-studio">Add captions</Link>
            <Link className="rounded bg-slate-700 px-3 py-1.5" href="/audio-studio">Audio Studio</Link>
            <Link className="rounded bg-slate-700 px-3 py-1.5" href="/reels-library">Reels Library</Link>
          </div>
        </div>
      )}
    </div>
  );
}