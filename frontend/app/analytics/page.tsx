"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { api, fmtBytes } from "@/lib/api8";

function Card({ label, value }: { label: string; value: any }) {
  return <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4"><div className="text-2xl font-bold text-white">{value ?? "-"}</div><div className="text-xs text-zinc-500">{label}</div></div>;
}

export default function AnalyticsPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/analytics").then(setD).catch((e) => setErr(e.message)); }, []);
  if (!d) return <div className="p-6 text-zinc-400">{err || "Loading..."}</div>;
  const max = Math.max(...d.clips_per_day.map((x: any) => x.count), 1);
  return (
    <div className="p-6 space-y-6 text-zinc-200">
      <h1 className="text-2xl font-bold text-white">AI Analytics</h1>
      <p className="text-xs text-zinc-500">Only real measured data from this computer. Empty values mean nothing has been measured yet.</p>
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Card label="Videos" value={d.videos.total} />
        <Card label="Video minutes" value={d.videos.total_minutes} />
        <Card label="Clips" value={d.clips.total} />
        <Card label="Ready clip minutes" value={d.clips.ready_minutes} />
        <Card label={`Avg AI score (${d.clips.scored_clips} clips)`} value={d.clips.avg_ai_score} />
        <Card label="Job success rate %" value={d.jobs.success_rate_percent} />
        <Card label="Highlights (Gemini)" value={d.highlights.by_source.gemini ?? 0} />
        <Card label="Highlights (local)" value={d.highlights.by_source.local ?? 0} />
      </div>
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="mb-3 font-semibold text-white">Clips created, last 14 days</h2>
        <div className="flex items-end gap-1 h-32">
          {d.clips_per_day.map((x: any) => (
            <div key={x.day} className="flex-1 flex flex-col items-center justify-end h-full" title={`${x.day}: ${x.count}`}>
              <span className="text-[10px] text-zinc-500">{x.count || ""}</span>
              <div className="w-full rounded-t bg-violet-500" style={{ height: `${(x.count / max) * 100}%`, minHeight: x.count ? 2 : 0 }} />
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="mb-3 font-semibold text-white">Jobs by type</h2>
        {d.jobs.by_type.length === 0 && <p className="text-zinc-500 text-sm">No jobs yet.</p>}
        <table className="w-full text-sm"><tbody>
          {d.jobs.by_type.map((t: any) => (
            <tr key={t.type} className="border-t border-zinc-800">
              <td className="py-1">{t.type}</td><td>{t.total} total</td><td className="text-green-400">{t.completed} ok</td>
              <td className="text-red-400">{t.failed} failed</td><td className="text-zinc-400">{t.avg_seconds != null ? t.avg_seconds + " s avg" : "-"}</td>
            </tr>
          ))}
        </tbody></table>
      </section>
      <p className="text-xs text-zinc-500">Total video size: {fmtBytes(d.videos.total_bytes)}</p>
    </div>
  );
}