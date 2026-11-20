"use client";
// CLIPFORGE-PHASE3 manual-clipper
import { useCallback, useEffect, useRef, useState } from "react";
import { Scissors, Play, Download, Trash2, Loader2, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link"; import { API, fmtClock, fmtDuration, watchJob, type ClipItem, type VideoItem } from "@/lib/api";

type ProxyState = { state: "none" | "building" | "ready" | "error"; progress: number; message?: string };
type ExportState = { jobId: number; clipId: number; status: string; progress: number; error: string | null };

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ready: "text-emerald-400", failed: "text-red-400", cancelled: "text-zinc-400",
    pending: "text-amber-300", processing: "text-violet-300",
  };
  return <span className={`text-xs font-medium ${map[status] ?? "text-zinc-400"}`}>{status}</span>;
}

export default function ManualClipperPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [offline, setOffline] = useState(false);
  const [src, setSrc] = useState("");
  const [usingProxy, setUsingProxy] = useState(false);
  const [proxy, setProxy] = useState<ProxyState>({ state: "none", progress: 0 });
  const [cur, setCur] = useState(0);
  const [dur, setDur] = useState(0);
  const [startStr, setStartStr] = useState("0");
  const [endStr, setEndStr] = useState("10");
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<"accurate" | "fast">("accurate");
  const [exp, setExp] = useState<ExportState | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [playClip, setPlayClip] = useState<ClipItem | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const resumeAt = useRef(0);
  const previewEnd = useRef<number | null>(null);
  const stops = useRef<Array<() => void>>([]);

  const video = videos.find((v) => v.id === videoId) ?? null;
  const total = dur || video?.duration_sec || 0;
  const startN = parseFloat(startStr);
  const endN = parseFloat(endStr);

  let rangeError: string | null = null;
  if (!Number.isFinite(startN) || !Number.isFinite(endN)) rangeError = "Enter start and end in seconds";
  else if (startN < 0) rangeError = "Start cannot be negative";
  else if (endN <= startN) rangeError = "End must be after start";
  else if (endN - startN < 0.5) rangeError = "Clip must be at least 0.5 seconds";
  else if (total && startN >= total) rangeError = "Start is beyond the end of the video";

  const exporting = exp !== null && (exp.status === "queued" || exp.status === "processing");

  const loadClips = useCallback(async (vid: number, focusId?: number) => {
    try {
      const r = await fetch(`${API}/api/clips?video_id=${vid}&limit=200`);
      if (!r.ok) return;
      const d = await r.json();
      setClips(d.items as ClipItem[]);
      if (focusId) {
        const found = (d.items as ClipItem[]).find((c) => c.id === focusId);
        if (found && found.status === "ready") setPlayClip(found);
      }
    } catch {
      /* backend offline: ignore */
    }
  }, []);

  // load video list
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/videos?limit=500`);
        if (!r.ok) throw new Error();
        const d = await r.json();
        const list: VideoItem[] = (d.items as VideoItem[]).filter((v) => v.has_video);
        setVideos(list);
        const q = new URLSearchParams(window.location.search).get("video");
        const id = q ? parseInt(q, 10) : NaN;
        if (Number.isFinite(id) && list.some((v) => v.id === id)) setVideoId(id);
      } catch {
        setOffline(true);
      }
    })();
  }, []);

  // stop SSE listeners when leaving the page
  useEffect(() => {
    const list = stops.current;
    return () => list.forEach((f) => f());
  }, []);

  // reset when a different video is selected
  useEffect(() => {
    if (videoId == null) return;
    const v = videos.find((x) => x.id === videoId);
    const d = v?.duration_sec ?? 30;
    setSrc(`${API}/api/videos/${videoId}/stream`);
    setUsingProxy(false);
    setProxy({ state: "none", progress: 0 });
    setCur(0);
    setDur(v?.duration_sec ?? 0);
    setStartStr("0");
    setEndStr(Math.min(30, d).toFixed(1));
    setTitle("");
    setExp(null);
    setPlayClip(null);
    setFormError(null);
    previewEnd.current = null;
    loadClips(videoId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  // while clips are exporting (even after a page refresh) keep the list fresh
  useEffect(() => {
    if (videoId == null) return;
    if (!clips.some((c) => c.status === "pending" || c.status === "processing")) return;
    const t = setInterval(() => loadClips(videoId), 2500);
    return () => clearInterval(t);
  }, [clips, videoId, loadClips]);

  // keyboard shortcuts: I = set start, O = set end
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      const el = videoRef.current;
      if (!el) return;
      if (e.key === "i" || e.key === "I") setStartStr(el.currentTime.toFixed(2));
      else if (e.key === "o" || e.key === "O") setEndStr(el.currentTime.toFixed(2));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function useProxyFile(vid: number) {
    setSrc(`${API}/api/videos/${vid}/proxy?t=${Date.now()}`);
    setUsingProxy(true);
    setProxy({ state: "ready", progress: 100 });
  }

  async function buildProxy(vid: number) {
    setProxy({ state: "building", progress: 0 });
    resumeAt.current = videoRef.current?.currentTime ?? 0;
    try {
      const r = await fetch(`${API}/api/videos/${vid}/proxy`, { method: "POST" });
      if (!r.ok) throw new Error("Could not start preview conversion");
      const d = await r.json();
      if (d.ready) {
        useProxyFile(vid);
        return;
      }
      const stop = watchJob(d.job_id, (j) => {
        if (j.status === "completed") useProxyFile(vid);
        else if (j.status === "failed" || j.status === "cancelled")
          setProxy({ state: "error", progress: 0, message: j.error ?? "Preview conversion failed" });
        else setProxy({ state: "building", progress: j.progress });
      });
      stops.current.push(stop);
    } catch (e) {
      setProxy({ state: "error", progress: 0, message: e instanceof Error ? e.message : "Preview failed" });
    }
  }

  function onVideoProblem() {
    if (videoId == null) return;
    if (usingProxy) {
      setProxy({ state: "error", progress: 0, message: "The preview file could not be played either" });
      return;
    }
    if (proxy.state === "building") return;
    void buildProxy(videoId);
  }

  function seek(t: number) {
    const el = videoRef.current;
    if (!el) return;
    previewEnd.current = null;
    el.currentTime = Math.max(0, Math.min(t, total || t));
    setCur(el.currentTime);
  }

  function previewSelection() {
    const el = videoRef.current;
    if (!el || rangeError) return;
    previewEnd.current = endN;
    el.currentTime = startN;
    void el.play();
  }

  async function exportClip() {
    if (!video || rangeError) return;
    setFormError(null);
    const vid = video.id;
    try {
      const r = await fetch(`${API}/api/clips`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_id: vid,
          start_sec: startN,
          end_sec: total ? Math.min(endN, total) : endN,
          title,
          mode,
        }),
      });
      const d = await r.json();
      if (!r.ok) {
        setFormError(typeof d.detail === "string" ? d.detail : "Invalid clip range");
        return;
      }
      const clipId: number = d.clip.id;
      setExp({ jobId: d.job_id, clipId, status: "queued", progress: 0, error: null });
      loadClips(vid);
      const stop = watchJob(d.job_id, (j) => {
        setExp({ jobId: d.job_id, clipId, status: j.status, progress: j.progress, error: j.error });
        if (j.status === "completed") loadClips(vid, clipId);
        else if (j.status === "failed" || j.status === "cancelled") loadClips(vid);
      });
      stops.current.push(stop);
    } catch {
      setFormError("Cannot reach the backend. Is it running?");
    }
  }

  async function cancelExport() {
    if (!exp) return;
    await fetch(`${API}/api/jobs/${exp.jobId}/cancel`, { method: "POST" }).catch(() => undefined);
  }

  async function removeClip(c: ClipItem) {
    if (!window.confirm(`Delete clip "${c.title}"?`)) return;
    const r = await fetch(`${API}/api/clips/${c.id}`, { method: "DELETE" });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      window.alert(d.detail ?? "Could not delete the clip");
      return;
    }
    if (playClip?.id === c.id) setPlayClip(null);
    if (videoId != null) loadClips(videoId);
  }

  const inputCls =
    "w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-violet-500";
  const btnCls = "rounded-lg bg-zinc-800 px-3 py-2 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-40";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Manual Clipper</h1>
          <p className="text-sm text-zinc-400">
            Pick a video, mark start and end, export a clip. Shortcuts: I = set start, O = set end.
          </p>
        </div>
        <select
          value={videoId ?? ""}
          onChange={(e) => setVideoId(e.target.value ? Number(e.target.value) : null)}
          className="w-72 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-violet-500"
        >
          <option value="">Select a video...</option>
          {videos.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({fmtDuration(v.duration_sec)})
            </option>
          ))}
        </select>
      </div>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}
      {!offline && videos.length === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-700 p-8 text-center text-sm text-zinc-400">
          No video files yet. Upload one first from Upload Videos.
        </div>
      )}
      {!offline && videos.length > 0 && !video && (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-700 p-8 text-center text-sm text-zinc-400">
          Select a video above to start clipping.
        </div>
      )}

      {video && (
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
              {proxy.state === "building" && (
                <div className="mb-3 flex items-center gap-2 rounded-lg bg-violet-950/40 p-3 text-sm text-violet-200">
                  <Loader2 size={16} className="animate-spin" />
                  Preparing a browser preview for this file... {Math.round(proxy.progress)}%
                </div>
              )}
              {proxy.state === "error" && (
                <div className="mb-3 flex items-center gap-2 rounded-lg bg-red-950/40 p-3 text-sm text-red-300">
                  <AlertTriangle size={16} /> {proxy.message}
                </div>
              )}
              <video
                key={src}
                ref={videoRef}
                src={src}
                controls
                className="max-h-[55vh] w-full rounded bg-black"
                onError={onVideoProblem}
                onLoadedMetadata={(e) => {
                  const el = e.currentTarget;
                  if (Number.isFinite(el.duration)) setDur(el.duration);
                  if (resumeAt.current > 0) {
                    el.currentTime = resumeAt.current;
                    resumeAt.current = 0;
                  }
                  if (el.videoWidth === 0) onVideoProblem(); // codec not supported by this browser
                }}
                onTimeUpdate={(e) => {
                  const el = e.currentTarget;
                  setCur(el.currentTime);
                  if (previewEnd.current != null && el.currentTime >= previewEnd.current) {
                    el.pause();
                    previewEnd.current = null;
                  }
                }}
              />

              <div
                className="relative mt-4 h-4 cursor-pointer rounded bg-zinc-800"
                title="Click to seek"
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  if (total > 0) seek(((e.clientX - rect.left) / rect.width) * total);
                }}
              >
                {total > 0 && !rangeError && (
                  <div
                    className="absolute top-0 h-4 rounded bg-violet-600/60"
                    style={{
                      left: `${(startN / total) * 100}%`,
                      width: `${((Math.min(endN, total) - startN) / total) * 100}%`,
                    }}
                  />
                )}
                {total > 0 && (
                  <div className="absolute -top-1 h-6 w-0.5 bg-white" style={{ left: `${(cur / total) * 100}%` }} />
                )}
              </div>
              <div className="mt-1 flex justify-between text-xs text-zinc-500">
                <span>{fmtClock(cur)}</span>
                <span>{fmtClock(total)}</span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-zinc-400">Start (seconds)</label>
                  <input className={inputCls} value={startStr} onChange={(e) => setStartStr(e.target.value)} inputMode="decimal" />
                  <div className="mt-2 flex gap-2">
                    <button className={btnCls} onClick={() => setStartStr((videoRef.current?.currentTime ?? 0).toFixed(2))}>
                      Set to now (I)
                    </button>
                    <button className={btnCls} onClick={() => seek(startN)} disabled={!Number.isFinite(startN)}>
                      Go to
                    </button>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-zinc-400">End (seconds)</label>
                  <input className={inputCls} value={endStr} onChange={(e) => setEndStr(e.target.value)} inputMode="decimal" />
                  <div className="mt-2 flex gap-2">
                    <button className={btnCls} onClick={() => setEndStr((videoRef.current?.currentTime ?? 0).toFixed(2))}>
                      Set to now (O)
                    </button>
                    <button className={btnCls} onClick={() => seek(endN)} disabled={!Number.isFinite(endN)}>
                      Go to
                    </button>
                  </div>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between">
                <p className={`text-sm ${rangeError ? "text-amber-300" : "text-zinc-300"}`}>
                  {rangeError ?? `Selected length: ${fmtClock(endN - startN)}`}
                </p>
                <button className={btnCls} onClick={previewSelection} disabled={!!rangeError}>
                  <span className="flex items-center gap-1"><Play size={14} /> Preview selection</span>
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
              <h2 className="font-semibold text-white">Export clip</h2>
              <label className="mt-3 block text-xs text-zinc-400">Title (optional)</label>
              <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
              <label className="mt-3 block text-xs text-zinc-400">Mode</label>
              <select className={inputCls} value={mode} onChange={(e) => setMode(e.target.value as "accurate" | "fast")}>
                <option value="accurate">Accurate (frame exact, re-encodes)</option>
                <option value="fast">Fast (no re-encode, keyframe aligned)</option>
              </select>
              <p className="mt-2 text-xs text-zinc-500">
                Fast is almost instant but may begin slightly before your start point. Your original video is never changed.
              </p>
              {formError && <p className="mt-3 text-sm text-red-400">{formError}</p>}
              <button
                onClick={exportClip}
                disabled={!!rangeError || exporting}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40"
              >
                <Scissors size={16} /> Export clip
              </button>

              {exp && (
                <div className="mt-4 rounded-lg border border-zinc-800 p-3 text-sm">
                  {exporting && (
                    <>
                      <div className="flex items-center justify-between text-violet-300">
                        <span className="flex items-center gap-2">
                          <Loader2 size={16} className="animate-spin" />
                          {exp.status === "queued" ? "Waiting in queue..." : `Exporting... ${Math.round(exp.progress)}%`}
                        </span>
                        <button onClick={cancelExport} className="text-xs text-zinc-400 hover:text-red-400">Cancel</button>
                      </div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded bg-zinc-800">
                        <div className="h-full bg-violet-500 transition-all" style={{ width: `${exp.progress}%` }} />
                      </div>
                    </>
                  )}
                  {exp.status === "completed" && (
                    <p className="flex items-center gap-2 text-emerald-400"><CheckCircle2 size={16} /> Clip is ready</p>
                  )}
                  {exp.status === "failed" && (
                    <p className="text-red-400"><AlertTriangle size={16} className="mr-1 inline" />{exp.error ?? "Export failed"}</p>
                  )}
                  {exp.status === "cancelled" && (
                    <p className="flex items-center gap-2 text-zinc-400"><XCircle size={16} /> Export cancelled</p>
                  )}
                </div>
              )}
            </div>

            {playClip && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                <p className="truncate text-sm font-medium text-white">{playClip.title}</p>
                <video
                  key={playClip.id}
                  controls
                  className="mt-2 max-h-64 w-full rounded bg-black"
                  src={`${API}/api/clips/${playClip.id}/stream`}
                />
                <a
                  href={`${API}/api/clips/${playClip.id}/download`}
                  className="mt-3 flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
                >
                  <Download size={16} /> Download clip
                </a>
              </div>
            )}

            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
              <h2 className="font-semibold text-white">Clips from this video ({clips.length})</h2>
              <div className="mt-3 space-y-2">
                {clips.length === 0 && <p className="text-sm text-zinc-500">No clips yet.</p>}
                {clips.map((c) => (
                  <div key={c.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 p-2">
                    {c.has_thumbnail ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={`${API}/api/clips/${c.id}/thumbnail`} alt="" className="h-12 w-20 rounded object-cover" />
                    ) : (
                      <div className="h-12 w-20 rounded bg-zinc-800" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-white">{c.title}</p>
                      <p className="text-xs text-zinc-500">
                        {fmtClock(c.start_sec)} - {fmtClock(c.end_sec)} <span className="mx-1">|</span>
                        <StatusBadge status={c.status} />
                      </p>
                    </div>
                    <div className="flex gap-1">
                      {c.status === "ready" && (
                        <>
                          <button onClick={() => setPlayClip(c)} className="rounded-md bg-zinc-800 p-2 hover:bg-zinc-700" title="Play">
                            <Play size={14} />
                          </button>
                          <Link href={`/audio-studio?clip=${c.id}`} className="rounded-md bg-zinc-800 px-2 py-2 text-xs text-violet-300 hover:bg-zinc-700" title="Add Music">Add Music</Link><a href={`${API}/api/clips/${c.id}/download`} className="rounded-md bg-zinc-800 p-2 hover:bg-zinc-700" title="Download">
                            <Download size={14} />
                          </a>
                        </>
                      )}
                      {c.status !== "pending" && c.status !== "processing" && (
                        <button onClick={() => removeClip(c)} className="rounded-md bg-zinc-800 p-2 text-red-400 hover:bg-red-950" title="Delete">
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
