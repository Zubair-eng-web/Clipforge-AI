"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Crop, Download, Loader2 } from "lucide-react";
import { API, fmtClock, watchJob, type ClipItem, type JobItem } from "@/lib/api";

const RATIOS = [
  { id: "9:16", label: "9:16 Vertical", hint: "Shorts, Reels, TikTok" },
  { id: "1:1", label: "1:1 Square", hint: "Instagram, LinkedIn" },
  { id: "16:9", label: "16:9 Wide", hint: "YouTube, desktop" },
];
const MODES = [
  { id: "face", label: "Face tracking", hint: "Crops around the speaker's face (OpenCV, CPU). Uses center crop if no face is found. Framing is fixed for the whole clip." },
  { id: "center", label: "Center crop", hint: "Fast. Keeps the middle of the frame." },
  { id: "blur", label: "Blurred background", hint: "Keeps the full frame and fills empty space with a blurred copy." },
];

export default function ReframingPage() {
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [ratio, setRatio] = useState("9:16");
  const [mode, setMode] = useState("face");
  const [job, setJob] = useState<JobItem | null>(null);
  const [resultId, setResultId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const stopRef = useRef<(() => void) | null>(null);

  const loadClips = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/clips?limit=200`);
      if (!r.ok) throw new Error();
      const d = await r.json();
      const ready = (d.items as ClipItem[]).filter((c) => c.status === "ready" && c.has_file);
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

  const running = job !== null && (job.status === "queued" || job.status === "processing");
  const selected = clips.find((c) => c.id === clipId) ?? null;

  async function start() {
    if (clipId === null) return;
    setError("");
    setResultId(null);
    setJob(null);
    try {
      const r = await fetch(`${API}/api/clips/${clipId}/reframe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ratio, mode }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(typeof d.detail === "string" ? d.detail : "Could not start reframing.");
        return;
      }
      setResultId(d.clip_id);
      setJob({ id: d.job_id, type: "reframe", video_id: null, status: "queued", progress: 0, error: null, created_at: "", updated_at: "" });
      stopRef.current?.();
      stopRef.current = watchJob(d.job_id, (j) => {
        setJob(j);
        if (["completed", "failed", "cancelled"].includes(j.status)) loadClips();
      });
    } catch {
      setError("Cannot reach the backend. Is it running?");
    }
  }

  async function cancel() {
    if (!job) return;
    await fetch(`${API}/api/jobs/${job.id}/cancel`, { method: "POST" }).catch(() => null);
  }

  return (
    <div className="max-w-5xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Crop size={24} className="text-violet-400" /> AI Reframing</h1>
      <p className="text-sm text-zinc-400">Convert a clip to 9:16, 1:1 or 16:9. The original clip is never changed; the result is saved as a new clip.</p>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}
      {!offline && clips.length === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-700 p-10 text-center text-sm text-zinc-400">
          No ready clips yet. Create one in the Manual Clipper or AI Auto Clipper first.
        </div>
      )}

      {clips.length > 0 && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <div className="space-y-5">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Source clip</p>
              <select
                value={clipId ?? ""}
                onChange={(e) => setClipId(Number(e.target.value))}
                disabled={running}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
              >
                {clips.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title} ({fmtClock(c.duration_sec)}, {c.aspect_ratio ?? "-"})
                  </option>
                ))}
              </select>
              {selected && (
                <video key={selected.id} controls className="mt-3 max-h-64 w-full rounded bg-black" src={`${API}/api/clips/${selected.id}/stream`} />
              )}
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Target format</p>
              <div className="grid grid-cols-3 gap-2">
                {RATIOS.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => setRatio(r.id)}
                    disabled={running}
                    className={`rounded-lg border p-3 text-left text-sm ${ratio === r.id ? "border-violet-500 bg-violet-600/20 text-white" : "border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-500"}`}
                  >
                    <div className="font-medium">{r.label}</div>
                    <div className="text-xs text-zinc-500">{r.hint}</div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Method</p>
              <div className="space-y-2">
                {MODES.map((m) => (
                  <label key={m.id} className={`block cursor-pointer rounded-lg border p-3 text-sm ${mode === m.id ? "border-violet-500 bg-violet-600/10" : "border-zinc-700 bg-zinc-900"}`}>
                    <input type="radio" name="mode" className="mr-2" checked={mode === m.id} onChange={() => setMode(m.id)} disabled={running} />
                    <span className="font-medium text-white">{m.label}</span>
                    <span className="mt-1 block text-xs text-zinc-500">{m.hint}</span>
                  </label>
                ))}
              </div>
            </div>

            <button
              onClick={start}
              disabled={running || clipId === null}
              className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
            >
              {running ? <Loader2 size={16} className="animate-spin" /> : <Crop size={16} />} Reframe clip
            </button>
          </div>

          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">Result</p>
            {error && <p className="mb-3 rounded-lg bg-zinc-900 p-3 text-sm text-red-400">{error}</p>}
            {job && running && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                <div className="h-2 overflow-hidden rounded bg-zinc-800">
                  <div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(job.progress, 100)}%` }} />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-zinc-400">
                  <span>{job.status === "queued" ? "Waiting in queue..." : `Reframing... ${Math.round(job.progress)}%`}</span>
                  <button onClick={cancel} className="text-red-400 hover:underline">Cancel</button>
                </div>
              </div>
            )}
            {job && job.status === "failed" && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-red-400">Failed: {job.error}</p>}
            {job && job.status === "cancelled" && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">Cancelled.</p>}
            {job && job.status === "completed" && resultId !== null && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                <video key={resultId} controls className="max-h-[60vh] w-full rounded bg-black" src={`${API}/api/clips/${resultId}/stream`} />
                <a href={`${API}/api/clips/${resultId}/download`} className="mt-3 inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-3 py-2 text-sm hover:bg-zinc-700">
                  <Download size={15} /> Download
                </a>
                <p className="mt-2 text-xs text-zinc-500">Also saved in Generated Clips.</p>
              </div>
            )}
            {!job && !error && <p className="text-sm text-zinc-500">Pick a clip, a format and a method, then press Reframe clip.</p>}
          </div>
        </div>
      )}
    </div>
  );
}