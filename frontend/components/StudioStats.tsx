"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Stats = {
  videos: number;
  clips: number;
  reels: number;
  captions: number;
  music_tracks: number;
  processing_jobs: number;
  queued_jobs: number;
  storage_bytes: number;
  recent_projects: { id: number; name: string; created_at: string | null }[];
  recent_exports: { name: string; folder: string; size_bytes: number; modified: string }[];
};

function fmtBytes(b: number): string {
  if (!b) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), u.length - 1);
  return `${(b / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${u[i]}`;
}

const ACTIONS = [
  { label: "Upload GTA 6 Video", href: "/upload" },
  { label: "Generate AI Highlights", href: "/ai-highlights" },
  { label: "Create Reels", href: "/reels" },
  { label: "Add Custom Music", href: "/music" },
  { label: "Generate Captions", href: "/captions" },
  { label: "Open Video Editor", href: "/editor" },
];

export default function StudioStats() {
  const [s, setS] = useState<Stats | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    fetch(`${API}/api/studio/stats`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => alive && setS(d))
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const cards: [string, string | number][] = s
    ? [
        ["Videos", s.videos],
        ["Clips", s.clips],
        ["Reels", s.reels],
        ["Captions", s.captions],
        ["Music tracks", s.music_tracks],
        ["Jobs running / queued", `${s.processing_jobs} / ${s.queued_jobs}`],
        ["Storage used", fmtBytes(s.storage_bytes)],
      ]
    : [];

  return (
    <section className="mb-6 space-y-4">
      <div className="flex flex-wrap gap-2">
        {ACTIONS.map((a) => (
          <Link key={a.href} href={a.href}
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 hover:bg-zinc-800">
            {a.label}
          </Link>
        ))}
      </div>
      {err && <p className="text-sm text-red-400">Stats load nahi hue ({err}). Backend chal raha hai?</p>}
      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {cards.map(([k, v]) => (
              <div key={k} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <div className="text-xs text-zinc-400">{k}</div>
                <div className="mt-1 text-xl font-semibold text-zinc-50">{v}</div>
              </div>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">Recent projects</div>
              {s.recent_projects.length === 0 && <div className="text-sm text-zinc-500">Abhi koi project nahi.</div>}
              {s.recent_projects.map((p) => (
                <div key={p.id} className="text-sm text-zinc-300">{p.name}</div>
              ))}
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">Recent exports</div>
              {s.recent_exports.length === 0 && <div className="text-sm text-zinc-500">Abhi koi export nahi.</div>}
              {s.recent_exports.map((e) => (
                <div key={e.folder + e.name} className="truncate text-sm text-zinc-300">
                  {e.name} <span className="text-zinc-500">({e.folder}, {fmtBytes(e.size_bytes)})</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  );
}