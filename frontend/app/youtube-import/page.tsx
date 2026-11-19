"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Loader2, Play, Search } from "lucide-react";
import { API, fmtDuration, watchJob, type JobItem } from "@/lib/api";

type LinkInfo = { title: string; duration: number | null; uploader: string | null; thumbnail: string | null; max_minutes: number };

export default function YoutubeImportPage() {
  const [url, setUrl] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [info, setInfo] = useState<LinkInfo | null>(null);
  const [checking, setChecking] = useState(false);
  const [job, setJob] = useState<JobItem | null>(null);
  const [error, setError] = useState("");
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => () => stopRef.current?.(), []);

  const running = job !== null && (job.status === "queued" || job.status === "processing");

  async function post(path: string, body: object) {
    const r = await fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : `Request failed (${r.status})`);
    return d;
  }

  async function check() {
    setError("");
    setInfo(null);
    setJob(null);
    setChecking(true);
    try {
      setInfo(await post("/api/youtube/info", { url }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read this link");
    } finally {
      setChecking(false);
    }
  }

  async function start() {
    setError("");
    setJob(null);
    try {
      const d = await post("/api/youtube/import", { url, confirm_rights: confirm });
      setJob({ id: d.job_id, type: "youtube_import", video_id: null, status: "queued", progress: 0, error: null, created_at: "", updated_at: "" });
      stopRef.current?.();
      stopRef.current = watchJob(d.job_id, (j) => setJob(j));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the import");
    }
  }

  async function cancel() {
    if (job) await fetch(`${API}/api/jobs/${job.id}/cancel`, { method: "POST" }).catch(() => null);
  }

  return (
    <div className="max-w-3xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Play size={24} className="text-violet-400" /> YouTube Import</h1>
      <p className="text-sm text-zinc-400">Download a video by link into your library. Only import videos you own or have permission to use.</p>

      <div className="mt-6 flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={running}
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white placeholder-zinc-500 outline-none focus:border-violet-500"
        />
        <button
          onClick={check}
          disabled={checking || running || url.trim().length < 8}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm hover:bg-zinc-700 disabled:opacity-50"
        >
          {checking ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />} Check link
        </button>
      </div>

      {error && <p className="mt-4 rounded-lg bg-zinc-900 p-3 text-sm text-red-400">{error}</p>}

      {info && (
        <div className="mt-4 flex gap-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
          {info.thumbnail && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={info.thumbnail} alt="" className="h-24 w-40 shrink-0 rounded object-cover" />
          )}
          <div className="min-w-0">
            <p className="truncate font-medium text-white">{info.title}</p>
            <p className="text-xs text-zinc-400">
              {info.uploader ?? "Unknown channel"} | {info.duration ? fmtDuration(info.duration) : "unknown length"} (limit {info.max_minutes} min)
            </p>
            <label className="mt-3 flex cursor-pointer items-start gap-2 text-sm text-zinc-300">
              <input type="checkbox" className="mt-1" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} disabled={running} />
              <span>I own this video or have permission to use it.</span>
            </label>
            <button
              onClick={start}
              disabled={!confirm || running}
              className="mt-3 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
            >
              Import video
            </button>
          </div>
        </div>
      )}

      {job && running && (
        <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="h-2 overflow-hidden rounded bg-zinc-800">
            <div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(job.progress, 100)}%` }} />
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-zinc-400">
            <span>{job.status === "queued" ? "Waiting in queue..." : `Downloading... ${Math.round(job.progress)}%`}</span>
            <button onClick={cancel} className="text-red-400 hover:underline">Cancel</button>
          </div>
        </div>
      )}
      {job && job.status === "failed" && (
        <p className="mt-4 rounded-lg bg-zinc-900 p-3 text-sm text-red-400">
          Import failed: {job.error}. If this keeps happening, update yt-dlp: <code>.\.venv\Scripts\python.exe -m pip install -U yt-dlp</code>
        </p>
      )}
      {job && job.status === "cancelled" && <p className="mt-4 rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">Import cancelled.</p>}
      {job && job.status === "completed" && (
        <div className="mt-4 rounded-xl border border-emerald-900 bg-emerald-950/30 p-4 text-sm">
          <p className="flex items-center gap-2 text-emerald-400"><CheckCircle2 size={16} /> Saved to your library.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {job.video_id && (
              <Link href={`/manual-clipper?video=${job.video_id}`} className="rounded-lg bg-violet-600 px-3 py-1.5 text-white hover:bg-violet-500">Open in Manual Clipper</Link>
            )}
            <Link href="/auto-clipper" className="rounded-lg bg-zinc-800 px-3 py-1.5 hover:bg-zinc-700">AI Auto Clipper</Link>
            <Link href="/library" className="rounded-lg bg-zinc-800 px-3 py-1.5 hover:bg-zinc-700">Video Library</Link>
          </div>
        </div>
      )}
    </div>
  );
}