"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Loader2, Smartphone } from "lucide-react";
import { API, api, rows } from "@/lib/api8";

type ClipRow = { id: number; title: string; status: string; duration_sec: number | null };
type Platform = { label: string; ratio: string; max_sec: number };
type Meta = { platforms: Record<string, Platform>; durations: number[]; modes: string[] };
type Track = { id: number; name: string; duration_sec: number | null };
type Part = { s: number; e: number };
type Started = { job_id: number; clip_id: number };

const inp = "rounded bg-slate-800 border border-slate-700 p-2 text-sm";
const r2 = (n: number) => Math.round(n * 100) / 100;
const fmt = (n: number) => `${r2(n)}s`;

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
  const [lenSel, setLenSel] = useState(""); // "" = keep full, "custom", or seconds
  const [customLen, setCustomLen] = useState(20);
  const [rangeMode, setRangeMode] = useState<"auto" | "manual">("auto");
  const [rStart, setRStart] = useState(0);
  const [rEnd, setREnd] = useState(0);
  const [split, setSplit] = useState(false);
  const [trimDead, setTrimDead] = useState(true);
  const [brightness, setBrightness] = useState(0);
  const [contrast, setContrast] = useState(1);
  const [saturation, setSaturation] = useState(1);
  const [origOn, setOrigOn] = useState(true);
  const [origVol, setOrigVol] = useState(1);
  const [music, setMusic] = useState<Record<number, number>>({});
  const [title, setTitle] = useState("");
  const [intro, setIntro] = useState({ on: false, text: "", seconds: 2, bg: "#111827", fg: "#ffffff" });
  const [outro, setOutro] = useState({ on: false, text: "Follow for more", seconds: 2, bg: "#111827", fg: "#ffffff" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [results, setResults] = useState<number[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

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

  const selClip = clips.find((c) => c.id === clipId) ?? null;
  const clipDur = Number(selClip?.duration_sec ?? 0);

  useEffect(() => {
    setRStart(0);
    setREnd(r2(clipDur));
  }, [clipId, clipDur]);

  const plat = meta?.platforms[platform];
  const durations = (meta?.durations ?? []).filter((s) => !plat || s <= plat.max_sec);
  const targetLen: number | null = lenSel === "" ? null : lenSel === "custom" ? Number(customLen) || null : Number(lenSel);

  const manual = rangeMode === "manual";
  const rangeS = manual ? rStart : 0;
  const rangeE = manual ? rEnd : clipDur;

  function buildParts(): Part[] {
    const out: Part[] = [];
    if (!split || !targetLen || targetLen <= 0) return out;
    let s = rangeS;
    while (rangeE - s >= targetLen - 1e-6 && out.length < 20) {
      out.push({ s: r2(s), e: r2(s + targetLen) });
      s += targetLen;
    }
    if (rangeE - s >= 3 && out.length < 20) out.push({ s: r2(s), e: r2(rangeE) });
    return out;
  }
  const parts = buildParts();

  // what the single reel will be (null = let the backend pick: auto window)
  const single: Part | null = manual
    ? { s: r2(rStart), e: r2(targetLen ? Math.min(rEnd, rStart + targetLen) : rEnd) }
    : null;
  const maxPart = split ? Math.max(0, ...parts.map((p) => p.e - p.s)) : 0;
  const singleLen = manual && single ? single.e - single.s : targetLen ? Math.min(targetLen, clipDur) : clipDur;
  const checkLen = split ? maxPart : manual ? singleLen : targetLen ?? 0;
  const cardSecs = (intro.on && intro.text.trim() ? intro.seconds : 0) + (outro.on && outro.text.trim() ? outro.seconds : 0);

  let problem = "";
  if (clipId === null) problem = "Choose a clip.";
  else if (manual && (rEnd - rStart < 1)) problem = "Manual range must be at least 1 second (end must be after start).";
  else if (manual && rEnd > clipDur + 0.01) problem = "End is after the end of the clip.";
  else if (split && !targetLen) problem = "Choose a length first (15, 30, ... or custom) to split into several reels.";
  else if (split && parts.length === 0) problem = "The range is shorter than the chosen length, so no reel can be made.";
  else if (plat && checkLen > plat.max_sec + 1e-6) problem = `${plat.label} allows at most ${plat.max_sec} seconds. Choose a shorter length or range.`;

  function watch(started: Started[]) {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      const states = await Promise.all(started.map((j) => api(`/api/jobs/${j.job_id}`).catch(() => null)));
      if (states.some((s) => s === null)) return; // keep polling
      const done = states.filter((s) => s && s.status !== "queued" && s.status !== "processing").length;
      const prog = states.reduce((a, s) => a + (s && s.status !== "queued" && s.status !== "processing" ? 100 : Math.min(100, Number(s?.progress) || 0)), 0) / started.length;
      setProgress(Math.round(prog));
      if (done < started.length) return;
      if (timer.current) clearInterval(timer.current);
      setBusy(false); setProgress(null);
      const okIds = started.filter((_, i) => states[i] && states[i].status === "completed").map((j) => j.clip_id);
      const failed = started.length - okIds.length;
      setResults(okIds);
      if (okIds.length === 0) setMsg("Reel failed: " + (states[0]?.error || "see History"));
      else setMsg(`${okIds.length} reel(s) ready${failed ? `, ${failed} failed or cancelled (see History)` : ""}. Original clip is untouched.`);
    }, 2000);
  }

  async function create() {
    if (clipId === null || problem) return;
    setBusy(true); setMsg(""); setResults([]); setProgress(0);
    const base: Record<string, unknown> = {
      clip_id: clipId, platform, size, mode, trim_dead_time: trimDead, brightness, contrast, saturation,
      original_audio_on: origOn, original_volume: origVol,
      music: Object.entries(music).map(([id, vol]) => ({ track_id: Number(id), volume: vol })),
    };
    if (mode === "manual") { base.cx = cx; base.cy = cy; }
    if (intro.on && intro.text.trim()) base.intro = { text: intro.text.trim(), seconds: intro.seconds, bg: intro.bg, fg: intro.fg };
    if (outro.on && outro.text.trim()) base.outro = { text: outro.text.trim(), seconds: outro.seconds, bg: outro.bg, fg: outro.fg };

    const jobs: Record<string, unknown>[] = [];
    const baseTitle = title.trim();
    if (split) {
      parts.forEach((p, i) => jobs.push({ ...base, start_sec: p.s, end_sec: p.e, title: `${baseTitle || selClip?.title || "Reel"} - part ${i + 1}`.slice(0, 200) }));
    } else if (single) {
      jobs.push({ ...base, start_sec: single.s, end_sec: single.e, title: baseTitle });
    } else {
      jobs.push({ ...base, ...(targetLen ? { target_sec: targetLen } : {}), title: baseTitle });
    }

    const started: Started[] = [];
    try {
      for (const body of jobs) {
        const d = await api("/api/reels-studio/create", { method: "POST", body: JSON.stringify(body) });
        started.push({ job_id: d.job_id as number, clip_id: d.clip_id as number });
      }
      watch(started);
    } catch (e) {
      if (started.length > 0) { setMsg(`Started ${started.length} of ${jobs.length} reels, then: ${(e as Error).message}`); watch(started); }
      else { setBusy(false); setProgress(null); setMsg((e as Error).message); }
    }
  }

  function here(): number {
    const v = videoRef.current;
    return v ? r2(v.currentTime) : 0;
  }

  const cardUi = (label: string, c: typeof intro, set: (v: typeof intro) => void) => (
    <div className={`rounded-lg border p-3 space-y-2 text-sm ${c.on ? "border-violet-500 bg-violet-500/10" : "border-slate-700"}`}>
      <label className="flex items-center gap-2 font-medium"><input type="checkbox" checked={c.on} onChange={(e) => set({ ...c, on: e.target.checked })} /> {label} card</label>
      {c.on && (
        <>
          <input className={inp + " w-full"} maxLength={80} placeholder="Text on the card" value={c.text} onChange={(e) => set({ ...c, text: e.target.value })} />
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="flex items-center gap-1">Seconds
              <select className={inp} value={c.seconds} onChange={(e) => set({ ...c, seconds: Number(e.target.value) })}>
                {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1">Background <input type="color" value={c.bg} onChange={(e) => set({ ...c, bg: e.target.value })} /></label>
            <label className="flex items-center gap-1">Text <input type="color" value={c.fg} onChange={(e) => set({ ...c, fg: e.target.value })} /></label>
          </div>
        </>
      )}
    </div>
  );

  const toggleTrack = (id: number) =>
    setMusic((m) => { const n = { ...m }; if (id in n) delete n[id]; else n[id] = 0.6; return n; });

  const btn = "rounded bg-slate-700 px-2 py-1 text-xs hover:bg-slate-600";

  return (
    <div className="p-6 space-y-5 max-w-6xl text-slate-200">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Smartphone className="w-7 h-7 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold">Reels &amp; Shorts Studio</h1>
            <p className="text-sm text-slate-400">Turn a clip into vertical reels: choose length and part of the clip, reframe, trim dead time, optional music from your library.</p>
          </div>
        </div>
        <Link href="/reels-library" className="rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Reels Library</Link>
      </div>

      {msg && <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">{msg}</div>}

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="space-y-3">
          <label className="block text-sm">Clip
            <select className={inp + " w-full mt-1"} value={clipId ?? ""} onChange={(e) => { setClipId(Number(e.target.value)); setResults([]); }}>
              {clips.length === 0 && <option value="">No ready clips (make one in Manual Clipper or Gaming Highlights)</option>}
              {clips.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.title} {c.duration_sec ? `(${Math.round(c.duration_sec)}s)` : ""}</option>)}
            </select>
          </label>
          {clipId !== null && (
            <video ref={videoRef} key={clipId} controls className="w-full rounded-lg bg-black max-h-[300px]" src={`${API}/api/clips/${clipId}/stream`} />
          )}
          <label className="block text-sm">Title (optional)
            <input className={inp + " w-full mt-1"} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          </label>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">Platform
              <select className={inp + " w-full mt-1"} value={platform} onChange={(e) => { setPlatform(e.target.value); setLenSel(""); }}>
                {meta && Object.entries(meta.platforms).map(([k, p]) => <option key={k} value={k}>{p.label} ({p.ratio})</option>)}
              </select>
            </label>
            <label className="text-sm">Size
              <select className={inp + " w-full mt-1"} value={size} onChange={(e) => setSize(e.target.value)}>
                <option value="1080">1080p (slower)</option>
                <option value="720">720p (faster, good for 8GB RAM)</option>
              </select>
            </label>
            <label className="text-sm">Reel length
              <select className={inp + " w-full mt-1"} value={lenSel} onChange={(e) => setLenSel(e.target.value)}>
                <option value="">Keep full clip</option>
                {durations.map((s) => <option key={s} value={s}>{s >= 180 && s % 60 === 0 ? `${s / 60} minutes` : `${s} seconds`}</option>)}
                <option value="custom">Custom seconds...</option>
              </select>
              {lenSel === "custom" && (
                <input type="number" min={1} max={plat?.max_sec ?? 600} value={customLen} onChange={(e) => setCustomLen(Number(e.target.value))} className={inp + " w-full mt-1"} />
              )}
            </label>
            <label className="text-sm">Reframe
              <select className={inp + " w-full mt-1"} value={mode} onChange={(e) => setMode(e.target.value)}>
                {(meta?.modes ?? ["face", "center", "blur", "manual"]).map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          </div>
          {plat && <p className="text-xs text-slate-500">{plat.label}: max {plat.max_sec}s. Longer reels are refused.</p>}
          {mode === "manual" && (
            <div className="grid grid-cols-2 gap-3 text-sm">
              <label>Horizontal {cx.toFixed(2)}<input type="range" min={0} max={1} step={0.01} value={cx} onChange={(e) => setCx(Number(e.target.value))} className="w-full" /></label>
              <label>Vertical {cy.toFixed(2)}<input type="range" min={0} max={1} step={0.01} value={cy} onChange={(e) => setCy(Number(e.target.value))} className="w-full" /></label>
            </div>
          )}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={trimDead} onChange={(e) => setTrimDead(e.target.checked)} /> Trim silent dead time at start/end (auto range only)</label>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <label>Brightness {brightness.toFixed(2)}<input type="range" min={-0.5} max={0.5} step={0.05} value={brightness} onChange={(e) => setBrightness(Number(e.target.value))} className="w-full" /></label>
            <label>Contrast {contrast.toFixed(2)}<input type="range" min={0.5} max={1.5} step={0.05} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} className="w-full" /></label>
            <label>Saturation {saturation.toFixed(2)}<input type="range" min={0} max={2} step={0.05} value={saturation} onChange={(e) => setSaturation(Number(e.target.value))} className="w-full" /></label>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700 p-4 space-y-3">
        <h2 className="font-semibold">Which part of the clip?</h2>
        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2"><input type="radio" checked={rangeMode === "auto"} onChange={() => setRangeMode("auto")} /> Auto (the most active part, AI picks)</label>
          <label className="flex items-center gap-2"><input type="radio" checked={rangeMode === "manual"} onChange={() => setRangeMode("manual")} /> Manual (I choose start and end)</label>
        </div>
        {manual && (
          <div className="space-y-3 text-sm">
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <div className="flex items-center justify-between"><span>Start: {fmt(rStart)}</span><button className={btn} onClick={() => setRStart(Math.min(here(), Math.max(rEnd - 1, 0)))}>Start = player time</button></div>
                <input type="range" min={0} max={Math.max(clipDur, 1)} step={0.1} value={rStart} onChange={(e) => setRStart(Math.min(Number(e.target.value), Math.max(rEnd - 1, 0)))} className="w-full" />
                <input type="number" min={0} max={clipDur} step={0.1} value={rStart} onChange={(e) => setRStart(Math.max(0, Number(e.target.value)))} className={inp + " w-28"} />
              </div>
              <div>
                <div className="flex items-center justify-between"><span>End: {fmt(rEnd)}</span><button className={btn} onClick={() => setREnd(Math.max(here(), rStart + 1))}>End = player time</button></div>
                <input type="range" min={0} max={Math.max(clipDur, 1)} step={0.1} value={rEnd} onChange={(e) => setREnd(Math.max(Number(e.target.value), rStart + 1))} className="w-full" />
                <input type="number" min={0} max={clipDur} step={0.1} value={rEnd} onChange={(e) => setREnd(Number(e.target.value))} className={inp + " w-28"} />
              </div>
            </div>
            <p className="text-xs text-slate-500">Play the clip, pause where you want, then press the button. Range: {fmt(rStart)} to {fmt(rEnd)} ({fmt(rEnd - rStart)}) of a {fmt(clipDur)} clip.</p>
          </div>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} />
          Make several reels: cut {manual ? "the range" : "the whole clip"} into equal parts of the chosen length
        </label>
        <div className="rounded-lg bg-slate-800/60 px-3 py-2 text-xs text-slate-300">
          {split
            ? (parts.length > 0
              ? <>This will make <b>{parts.length}</b> reel(s): {parts.slice(0, 6).map((p) => `${fmt(p.s)}-${fmt(p.e)}`).join(", ")}{parts.length > 6 ? ", ..." : ""}. Parts run one after another (max 20).</>
              : <>Pick a length (above) that fits inside the range.</>)
            : manual
              ? <>One reel from {fmt(single?.s ?? 0)} to {fmt(single?.e ?? 0)} ({fmt(singleLen)}).{targetLen && rEnd - rStart > targetLen ? " It is cut to the chosen length from the start." : ""}</>
              : targetLen
                ? <>One reel of about {targetLen}s, taken from the most active part of the clip.</>
                : <>One reel from the full clip ({fmt(clipDur)}){plat && clipDur > plat.max_sec ? `; it will be cut to ${plat.max_sec}s for ${plat.label}` : ""}.</>}
          {cardSecs > 0 && <> Intro/outro cards add {cardSecs}s to every reel.</>}
        </div>
        {problem && <p className="text-sm text-red-400">{problem}</p>}
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

      <div className="rounded-xl border border-slate-700 p-4 space-y-3">
        <h2 className="font-semibold">Intro / Outro (optional)</h2>
        <p className="text-xs text-slate-500">A short text card (1 to 5 seconds) before or after the reel. It adds to the final length.</p>
        <div className="grid sm:grid-cols-2 gap-3">
          {cardUi("Intro", intro, setIntro)}
          {cardUi("Outro", outro, setOutro)}
        </div>
      </div>

      <button disabled={busy || clipId === null || !!problem} onClick={create}
        className="inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-5 py-2.5 font-medium">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Smartphone className="w-4 h-4" />}
        {busy ? `Creating${progress !== null ? " " + progress + "%" : "..."}` : split && parts.length > 1 ? `Create ${parts.length} Reels` : "Create Reel"}
      </button>

      {results.length > 0 && (
        <div className="rounded-xl border border-emerald-600/50 p-4 space-y-4">
          <h2 className="font-semibold">{results.length === 1 ? `Your reel (clip #${results[0]})` : `Your ${results.length} reels`}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {results.map((id) => (
              <div key={id} className="space-y-2">
                <video controls className="max-h-[420px] rounded-lg bg-black" src={`${API}/api/clips/${id}/stream`} />
                <div className="flex flex-wrap gap-2 text-sm">
                  <span className="text-xs text-slate-400">#{id}</span>
                  <a className="rounded bg-slate-700 px-3 py-1" href={`${API}/api/clips/${id}/download`}>Download MP4</a>
                  
                </div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-3 text-sm">
            <Link className="rounded bg-slate-700 px-3 py-1.5" href="/captions-studio">Add captions</Link>
            <Link className="rounded bg-slate-700 px-3 py-1.5" href="/audio-studio">Audio Studio</Link>
            <Link className="rounded bg-slate-700 px-3 py-1.5" href="/reels-library">Reels Library</Link>
          </div>
        </div>
      )}
    </div>
  );
}