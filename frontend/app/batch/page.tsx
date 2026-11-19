"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Layers, Loader2 } from "lucide-react";
import { API, fmtDuration, type VideoItem } from "@/lib/api";

type Row = {
  job_id: number; video_id: number | null; video_name: string; status: string; progress: number;
  error: string | null; clips_total: number; clips_ready: number; clips_active: number; created_at: string;
};

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
      const r = await fetch(`${API}/api/batch/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_ids: selected, count, mode, use_gemini: useGemini }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        setMsg(typeof d.detail === "string" ? d.detail : "Could not start the batch.");
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

  return (
    <div className="max-w-5xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Layers size={24} className="text-violet-400" /> Batch Processing</h1>
      <p className="text-sm text-zinc-400">Select several videos. Each one is analyzed (if needed) and its best clips are exported automatically. Videos run one after another to protect your RAM.</p>

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
          <button onClick={start} disabled={busy || selected.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Layers size={16} />} Start batch
          </button>
          {msg && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}
        </div>
      </div>

      <div className="mt-8 flex items-center justify-between">
        <h2 className="font-semibold text-white">Batch jobs</h2>
        <Link href="/clips" className="text-sm text-violet-400 hover:underline">Open Generated Clips</Link>
      </div>
      <div className="mt-2 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
            <tr><th className="px-4 py-3">Video</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Clips</th><th className="px-4 py-3 text-right"> </th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.job_id} className="border-b border-zinc-800/60 last:border-0">
                <td className="max-w-xs px-4 py-3">
                  <div className="truncate text-zinc-200">{r.video_name}</div>
                  {(r.status === "processing" || r.status === "queued") && (
                    <div className="mt-1 h-1.5 overflow-hidden rounded bg-zinc-800">
                      <div className="h-1.5 bg-violet-500 transition-all" style={{ width: `${Math.min(r.progress, 100)}%` }} />
                    </div>
                  )}
                  {r.error && <div className="mt-1 text-xs text-red-400">{r.error}</div>}
                </td>
                <td className={`px-4 py-3 text-xs font-medium ${COLORS[r.status] ?? "text-zinc-400"}`}>
                  {r.status}{r.status === "processing" ? ` ${Math.round(r.progress)}%` : ""}
                </td>
                <td className="px-4 py-3 text-xs text-zinc-400">{r.clips_ready} ready{r.clips_active ? `, ${r.clips_active} exporting` : ""}</td>
                <td className="px-4 py-3 text-right">
                  {(r.status === "queued" || r.status === "processing") && (
                    <button onClick={() => cancel(r.job_id)} className="text-xs text-red-400 hover:underline">Cancel</button>
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