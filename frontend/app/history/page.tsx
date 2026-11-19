"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api8";

const color: Record<string, string> = {
  queued: "text-zinc-400", processing: "text-yellow-300", completed: "text-green-400", ready: "text-green-400",
  failed: "text-red-400", cancelled: "text-orange-400",
};

export default function HistoryPage() {
  const [sum, setSum] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [hist, setHist] = useState<any[]>([]);
  const [kind, setKind] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      setSum(await api("/api/queue/summary"));
      setJobs((await api("/api/jobs?limit=30")).items);
      setHist((await api("/api/history?limit=60" + (kind ? "&kind=" + kind : ""))).items);
    } catch (e: any) { setErr(e.message); }
  }, [kind]);
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, [load]);

  async function act(path: string) {
    setErr("");
    try { await api(path, { method: "POST" }); load(); } catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="p-6 space-y-6 text-zinc-200">
      <h1 className="text-2xl font-bold text-white">History and Queue</h1>
      {err && <p className="text-red-400 text-sm">{err}</p>}
      {sum && (
        <div className="flex flex-wrap gap-3">
          {Object.entries(sum.counts).map(([k, v]) => (
            <div key={k} className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2"><div className={`text-xl font-bold ${color[k]}`}>{String(v)}</div><div className="text-xs text-zinc-500">{k}</div></div>
          ))}
          <button onClick={() => act("/api/queue/cancel-queued")} className="rounded border border-zinc-700 px-3 text-sm">Cancel all queued</button>
          <button onClick={() => act("/api/queue/clear-finished")} className="rounded border border-zinc-700 px-3 text-sm">Clear finished</button>
        </div>
      )}
      <section>
        <h2 className="mb-2 font-semibold text-white">Latest jobs</h2>
        <div className="rounded-xl border border-zinc-800 divide-y divide-zinc-800">
          {jobs.length === 0 && <p className="p-3 text-zinc-500">No jobs yet.</p>}
          {jobs.map((j) => (
            <div key={j.id} className="flex items-center gap-3 p-3 text-sm">
              <span className="w-12 text-zinc-500">#{j.id}</span>
              <span className="w-40 truncate">{j.type}</span>
              <span className={`w-24 ${color[j.status]}`}>{j.status}</span>
              <div className="flex-1 h-2 rounded bg-zinc-800"><div className="h-2 rounded bg-violet-500" style={{ width: `${j.progress}%` }} /></div>
              <span className="w-32 truncate text-xs text-red-400" title={j.error || ""}>{j.error || ""}</span>
              {(j.status === "queued" || j.status === "processing") && <button onClick={() => act(`/api/jobs/${j.id}/cancel`)} className="text-xs text-orange-400">Cancel</button>}
              {(j.status === "failed" || j.status === "cancelled") && <button onClick={() => act(`/api/queue/${j.id}/retry`)} className="text-xs text-violet-300">Retry</button>}
            </div>
          ))}
        </div>
      </section>
      <section>
        <div className="mb-2 flex items-center gap-3">
          <h2 className="font-semibold text-white">Timeline</h2>
          <select className="rounded bg-zinc-800 px-2 py-1 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All</option><option value="video">Videos</option><option value="clip">Clips</option>
            <option value="job">Jobs</option><option value="thumbnail">Thumbnails</option>
          </select>
        </div>
        <div className="rounded-xl border border-zinc-800 divide-y divide-zinc-800">
          {hist.map((h) => (
            <div key={h.kind + h.id} className="flex gap-3 p-3 text-sm">
              <span className="w-24 text-zinc-500">{h.kind}</span>
              <span className="flex-1 truncate">{h.title}</span>
              <span className={`w-24 ${color[h.status] || "text-zinc-400"}`}>{h.status}</span>
              <span className="w-44 text-xs text-zinc-500">{new Date(h.at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}