"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Download, Film, Loader2, Plus, X } from "lucide-react";
import { API, fmtClock, watchJob, type ClipItem, type JobItem } from "@/lib/api";

function Slider({ label, value, min, max, step, onChange, disabled, show }: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; disabled: boolean; show: string;
}) {
  return (
    <div>
      <p className="mb-1 text-xs text-zinc-400">{label}: <span className="text-zinc-200">{show}</span></p>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))} className="w-full" />
    </div>
  );
}

export default function EditorPage() {
  const [tab, setTab] = useState<"edit" | "merge">("edit");
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [trimStart, setTrimStart] = useState("0");
  const [trimEnd, setTrimEnd] = useState("");
  const [speed, setSpeed] = useState(1);
  const [volume, setVolume] = useState(1);
  const [mute, setMute] = useState(false);
  const [fade, setFade] = useState(0);
  const [brightness, setBrightness] = useState(0);
  const [contrast, setContrast] = useState(1);
  const [saturation, setSaturation] = useState(1);
  const [flipH, setFlipH] = useState(false);
  const [order, setOrder] = useState<number[]>([]);
  const [mergeRatio, setMergeRatio] = useState("first");
  const [job, setJob] = useState<JobItem | null>(null);
  const [resultId, setResultId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const stopRef = useRef<(() => void) | null>(null);

  const selected = clips.find((c) => c.id === clipId) ?? null;
  const running = job !== null && (job.status === "queued" || job.status === "processing");

  const loadClips = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/clips?limit=200`);
      if (!r.ok) throw new Error();
      const ready = ((await r.json()).items as ClipItem[]).filter((c) => c.status === "ready" && c.has_file);
      setClips(ready);
      setClipId((cur) => cur ?? (ready[0]?.id ?? null));
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    loadClips();
    return () => stopRef.current?.();
  }, [loadClips]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.playbackRate = speed;
    v.volume = mute ? 0 : Math.min(volume, 1);
  }, [speed, volume, mute, clipId, tab]);

  function resetOps() {
    setTrimStart("0"); setTrimEnd(""); setSpeed(1); setVolume(1); setMute(false); setFade(0);
    setBrightness(0); setContrast(1); setSaturation(1); setFlipH(false);
  }

  function fromPlayhead(which: "start" | "end") {
    const v = videoRef.current;
    if (!v) return;
    const t = (Math.round(v.currentTime * 10) / 10).toString();
    if (which === "start") setTrimStart(t); else setTrimEnd(t);
  }

  async function run(path: string, body: object) {
    setError(""); setResultId(null); setJob(null);
    try {
      const r = await fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        const detail = Array.isArray(d.detail) ? d.detail[0]?.msg : d.detail;
        setError(typeof detail === "string" ? detail : "Request failed");
        return;
      }
      setResultId(d.clip_id);
      setJob({ id: d.job_id, type: "", video_id: null, status: "queued", progress: 0, error: null, created_at: "", updated_at: "" });
      stopRef.current?.();
      stopRef.current = watchJob(d.job_id, (j) => {
        setJob(j);
        if (["completed", "failed", "cancelled"].includes(j.status)) loadClips();
      });
    } catch {
      setError("Cannot reach the backend. Is it running?");
    }
  }

  function applyEdit() {
    if (clipId === null) return;
    const endTxt = trimEnd.trim();
    run(`/api/clips/${clipId}/edit`, {
      trim_start: Number(trimStart) || 0,
      trim_end: endTxt === "" ? null : Number(endTxt),
      speed, volume, mute, fade_seconds: fade, brightness, contrast, saturation, flip_h: flipH,
    });
  }

  function applyMerge() {
    run("/api/editor/merge", { clip_ids: order, ratio: mergeRatio });
  }

  async function cancel() {
    if (job) await fetch(`${API}/api/jobs/${job.id}/cancel`, { method: "POST" }).catch(() => null);
  }

  function move(i: number, d: number) {
    setOrder((o) => {
      const j = i + d;
      if (j < 0 || j >= o.length) return o;
      const n = [...o];
      [n[i], n[j]] = [n[j], n[i]];
      return n;
    });
  }

  const titleOf = (id: number) => clips.find((c) => c.id === id)?.title ?? `Clip ${id}`;
  const tabBtn = (id: "edit" | "merge", label: string) => (
    <button onClick={() => setTab(id)} disabled={running}
      className={`rounded-lg px-4 py-2 text-sm ${tab === id ? "bg-violet-600 text-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"}`}>{label}</button>
  );

  return (
    <div className="max-w-6xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Film size={24} className="text-violet-400" /> Video Editor</h1>
      <p className="text-sm text-zinc-400">Edit a clip or join several clips. Every result is saved as a new clip; originals are never changed.</p>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}
      {!offline && clips.length === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-700 p-10 text-center text-sm text-zinc-400">
          No ready clips yet. Create clips first (Manual Clipper or AI Auto Clipper).
        </div>
      )}

      {clips.length > 0 && (
        <>
          <div className="mt-6 flex gap-2">{tabBtn("edit", "Edit one clip")}{tabBtn("merge", "Merge clips")}</div>
          <div className="mt-4 grid gap-6 lg:grid-cols-2">
            {tab === "edit" ? (
              <div className="space-y-4">
                <select value={clipId ?? ""} onChange={(e) => { setClipId(Number(e.target.value)); resetOps(); }} disabled={running}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white">
                  {clips.map((c) => <option key={c.id} value={c.id}>{c.title} ({fmtClock(c.duration_sec)})</option>)}
                </select>
                {selected && (
                  <video ref={videoRef} key={selected.id} controls className="max-h-72 w-full rounded bg-black"
                    style={{ filter: `brightness(${1 + brightness}) contrast(${contrast}) saturate(${saturation})`, transform: flipH ? "scaleX(-1)" : undefined }}
                    src={`${API}/api/clips/${selected.id}/stream`} />
                )}
                <p className="text-xs text-zinc-500">Preview is approximate. The saved clip uses FFmpeg.</p>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="mb-1 text-xs text-zinc-400">Trim start (s)</p>
                    <input value={trimStart} onChange={(e) => setTrimStart(e.target.value)} disabled={running}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white" />
                    <button onClick={() => fromPlayhead("start")} className="mt-1 text-xs text-violet-400 hover:underline">Use playhead</button>
                  </div>
                  <div>
                    <p className="mb-1 text-xs text-zinc-400">Trim end (s, empty = end)</p>
                    <input value={trimEnd} onChange={(e) => setTrimEnd(e.target.value)} disabled={running}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-white" />
                    <button onClick={() => fromPlayhead("end")} className="mt-1 text-xs text-violet-400 hover:underline">Use playhead</button>
                  </div>
                </div>
                <Slider label="Speed" value={speed} min={0.5} max={2} step={0.25} onChange={setSpeed} disabled={running} show={`${speed}x`} />
                <Slider label="Volume" value={volume} min={0} max={2} step={0.1} onChange={setVolume} disabled={running || mute} show={`${Math.round(volume * 100)}%`} />
                <label className="flex items-center gap-2 text-sm text-zinc-300"><input type="checkbox" checked={mute} onChange={(e) => setMute(e.target.checked)} disabled={running} /> Mute audio</label>
                <Slider label="Fade in / out" value={fade} min={0} max={3} step={0.5} onChange={setFade} disabled={running} show={fade === 0 ? "off" : `${fade}s`} />
                <Slider label="Brightness" value={brightness} min={-0.5} max={0.5} step={0.05} onChange={setBrightness} disabled={running} show={brightness.toFixed(2)} />
                <Slider label="Contrast" value={contrast} min={0.5} max={1.5} step={0.05} onChange={setContrast} disabled={running} show={contrast.toFixed(2)} />
                <Slider label="Saturation" value={saturation} min={0} max={2} step={0.05} onChange={setSaturation} disabled={running} show={saturation.toFixed(2)} />
                <label className="flex items-center gap-2 text-sm text-zinc-300"><input type="checkbox" checked={flipH} onChange={(e) => setFlipH(e.target.checked)} disabled={running} /> Flip horizontally</label>
                <div className="flex gap-2">
                  <button onClick={applyEdit} disabled={running || clipId === null}
                    className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
                    {running ? <Loader2 size={16} className="animate-spin" /> : <Film size={16} />} Apply edits
                  </button>
                  <button onClick={resetOps} disabled={running} className="rounded-lg bg-zinc-800 px-4 py-2.5 text-sm hover:bg-zinc-700">Reset</button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Add clips (in order)</p>
                  <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-900/60 p-2">
                    {clips.map((c) => (
                      <button key={c.id} onClick={() => setOrder((o) => (o.length < 10 ? [...o, c.id] : o))} disabled={running}
                        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm text-zinc-300 hover:bg-zinc-800">
                        <span className="truncate">{c.title}</span>
                        <span className="ml-2 flex shrink-0 items-center gap-1 text-xs text-zinc-500">{fmtClock(c.duration_sec)} <Plus size={14} /></span>
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Merge order ({order.length}/10)</p>
                  {order.length === 0 && <p className="text-sm text-zinc-500">Pick at least 2 clips above.</p>}
                  <div className="space-y-1">
                    {order.map((id, i) => (
                      <div key={`${id}-${i}`} className="flex items-center justify-between rounded-md bg-zinc-800/70 px-2 py-1.5 text-sm">
                        <span className="truncate text-zinc-200">{i + 1}. {titleOf(id)}</span>
                        <span className="flex shrink-0 gap-1">
                          <button onClick={() => move(i, -1)} className="rounded p-1 hover:bg-zinc-700"><ArrowUp size={14} /></button>
                          <button onClick={() => move(i, 1)} className="rounded p-1 hover:bg-zinc-700"><ArrowDown size={14} /></button>
                          <button onClick={() => setOrder((o) => o.filter((_, k) => k !== i))} className="rounded p-1 text-red-400 hover:bg-zinc-700"><X size={14} /></button>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs text-zinc-400">Output size</p>
                  <select value={mergeRatio} onChange={(e) => setMergeRatio(e.target.value)} disabled={running}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white">
                    <option value="first">Same as the first clip</option>
                    <option value="9:16">9:16 vertical (720x1280)</option>
                    <option value="1:1">1:1 square (720x720)</option>
                    <option value="16:9">16:9 wide (1280x720)</option>
                  </select>
                </div>
                <button onClick={applyMerge} disabled={running || order.length < 2}
                  className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
                  {running ? <Loader2 size={16} className="animate-spin" /> : <Film size={16} />} Merge clips
                </button>
              </div>
            )}

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Result</p>
              {error && <p className="mb-3 rounded-lg bg-zinc-900 p-3 text-sm text-red-400">{error}</p>}
              {job && running && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                  <div className="h-2 overflow-hidden rounded bg-zinc-800">
                    <div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(job.progress, 100)}%` }} />
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs text-zinc-400">
                    <span>{job.status === "queued" ? "Waiting in queue..." : `Working... ${Math.round(job.progress)}%`}</span>
                    <button onClick={cancel} className="text-red-400 hover:underline">Cancel</button>
                  </div>
                </div>
              )}
              {job && job.status === "failed" && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-red-400">Failed: {job.error}</p>}
              {job && job.status === "cancelled" && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">Cancelled.</p>}
              {job && job.status === "completed" && resultId !== null && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                  <video key={resultId} controls className="max-h-[60vh] w-full rounded bg-black" src={`${API}/api/clips/${resultId}/stream`} />
                  <a href={`${API}/api/clips/${resultId}/download`} className="mt-3 inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-3 py-2 text-sm hover:bg-zinc-700"><Download size={15} /> Download</a>
                  <p className="mt-2 text-xs text-zinc-500">Also saved in Generated Clips.</p>
                </div>
              )}
              {!job && !error && <p className="text-sm text-zinc-500">Your edited clip will appear here.</p>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}