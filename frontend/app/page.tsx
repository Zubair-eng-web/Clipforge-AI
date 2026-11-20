"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Video, Clapperboard, CheckCircle2, Loader2, AlertTriangle, HardDrive, Upload, Sparkles } from "lucide-react";
import StudioStats from "../components/StudioStats";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Stats = {
  total_videos: number; total_clips: number; completed_jobs: number;
  processing_jobs: number; failed_jobs: number; storage_bytes: number;
  recent_videos: { id: number; name: string; created_at: string }[];
  recent_clips: { id: number; title: string; created_at: string }[];
};

function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
  return `${n.toFixed(1)} ${units[i]}`;
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/dashboard`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setStats)
      .catch(() => setError(true));
  }, []);

  const cards = stats
    ? [
        { label: "Uploaded Videos", value: stats.total_videos, icon: Video },
        { label: "Generated Clips", value: stats.total_clips, icon: Clapperboard },
        { label: "Completed Jobs", value: stats.completed_jobs, icon: CheckCircle2 },
        { label: "Processing", value: stats.processing_jobs, icon: Loader2 },
        { label: "Failed Jobs", value: stats.failed_jobs, icon: AlertTriangle },
        { label: "Storage Used", value: fmtBytes(stats.storage_bytes), icon: HardDrive },
      ]
    : [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-zinc-400">Turn Long Videos Into Powerful Clips.</p>
        </div>
        <div className="flex gap-3">
          <Link href="/upload" className="flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm hover:bg-zinc-700">
            <Upload size={16} /> Quick Upload
          </Link>
          <Link href="/auto-clipper" className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500">
            <Sparkles size={16} /> Start AI Clipping
          </Link>
        </div>
      </div>

      {error && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-backend.ps1</code>
        </div>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-3">
        {cards.map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-sm">{label}</span>
              <Icon size={18} />
            </div>
            <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <Panel title="Recent Projects" empty="No videos yet. Upload one to get started."
          items={stats?.recent_videos.map((v) => v.name) ?? []} />
        <Panel title="Recently Generated Clips" empty="No clips generated yet."
          items={stats?.recent_clips.map((c) => c.title) ?? []} />
      </div>
    </div>
  );
}

function Panel({ title, empty, items }: { title: string; empty: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
<StudioStats />
      <h2 className="mb-3 font-semibold text-white">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-zinc-500">{empty}</p>
      ) : (
        <ul className="space-y-2 text-sm text-zinc-300">
          {items.map((t, i) => (
            <li key={i} className="rounded-md bg-zinc-800/60 px-3 py-2">{t}</li>
          ))}
        </ul>
      )}
    </div>
  );
}