"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Reel = {
  id: number; title: string; platform: string; aspect: string;
  width: number; height: number; duration_sec: number | null; status: string; created_at: string | null;
};

export default function ReelsLibraryPage() {
  const [reels, setReels] = useState<Reel[] | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    fetch(`${API}/api/reels`)
      .then((r) => r.json())
      .then(setReels)
      .catch((e) => setErr(String(e)));
  }, []);
  useEffect(load, [load]);

  async function del(id: number) {
    if (!confirm("Ye reel delete karein? Original video safe rahegi.")) return;
    await fetch(`${API}/api/reels/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="space-y-4 p-6 text-zinc-200">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-zinc-50">Reels Library</h1>
        <Link href="/reels" className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm hover:bg-zinc-800">
          Reels & Shorts Studio
        </Link>
      </div>
      {err && <p className="text-red-400">Reels load nahi hue ({err}).</p>}
      {reels && reels.length === 0 && <p className="text-sm text-zinc-500">Abhi koi reel nahi bani.</p>}
      <div className="grid gap-3 md:grid-cols-3">
        {reels?.map((r) => (
          <div key={r.id} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
            <div className="font-medium text-zinc-50">{r.title}</div>
            <div className="mt-1 text-xs text-zinc-400">
              {r.platform} | {r.aspect} | {r.width}x{r.height}
              {r.duration_sec ? ` | ${r.duration_sec.toFixed(1)}s` : ""} | {r.status}
            </div>
            <button onClick={() => del(r.id)} className="mt-3 text-xs text-red-400 hover:underline">Delete</button>
          </div>
        ))}
      </div>
    </div>
  );
}