"use client";
// CLIPFORGE-PHASE3 generated-clips
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Download, Trash2, Play, X, Loader2 } from "lucide-react";
import { API, fmtClock, type ClipItem } from "@/lib/api";

export default function GeneratedClipsPage() {
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [preview, setPreview] = useState<ClipItem | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/clips?limit=200`);
      if (!r.ok) throw new Error();
      const d = await r.json();
      setClips(d.items);
      setTotal(d.total);
      setOffline(false);
    } catch {
      setOffline(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!clips.some((c) => c.status === "pending" || c.status === "processing")) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [clips, load]);

  async function remove(c: ClipItem) {
    if (!window.confirm(`Permanently delete "${c.title}"?`)) return;
    const r = await fetch(`${API}/api/clips/${c.id}`, { method: "DELETE" });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      window.alert(d.detail ?? "Could not delete the clip");
      return;
    }
    if (preview?.id === c.id) setPreview(null);
    load();
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Generated Clips</h1>
          <p className="text-sm text-zinc-400">{total} clip{total === 1 ? "" : "s"} saved locally</p>
        </div>
        <Link href="/manual-clipper" className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500">
          New clip
        </Link>
      </div>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}
      {!loading && !offline && clips.length === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-700 p-10 text-center text-sm text-zinc-400">
          No clips yet. Use the Manual Clipper to create your first one.
        </div>
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {clips.map((c) => (
          <div key={c.id} className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
            <div className="relative flex h-40 items-center justify-center bg-zinc-950">
              {c.has_thumbnail ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={`${API}/api/clips/${c.id}/thumbnail`} alt="" className="h-full w-full object-cover" />
              ) : c.status === "pending" || c.status === "processing" ? (
                <Loader2 className="animate-spin text-violet-400" />
              ) : (
                <span className="text-xs text-zinc-600">no thumbnail</span>
              )}
            </div>
            <div className="p-3">
              <p className="truncate font-medium text-white">{c.title}</p>
              <p className="text-xs text-zinc-500">
                {fmtClock(c.duration_sec)} | {c.aspect_ratio ?? "-"} | {c.status}
              </p>
              <div className="mt-3 flex gap-2">
                {c.status === "ready" && (
                  <>
                    <button onClick={() => setPreview(c)} className="rounded-md bg-zinc-800 p-2 hover:bg-zinc-700" title="Play">
                      <Play size={15} />
                    </button>
                    <Link href={`/audio-studio?clip=${c.id}`} className="rounded-md bg-zinc-800 px-2 py-2 text-xs text-violet-300 hover:bg-zinc-700" title="Add Music">Add Music</Link><a href={`${API}/api/clips/${c.id}/download`} className="rounded-md bg-zinc-800 p-2 hover:bg-zinc-700" title="Download">
                      <Download size={15} />
                    </a>
                  </>
                )}
                {c.status !== "pending" && c.status !== "processing" && (
                  <button onClick={() => remove(c)} className="rounded-md bg-zinc-800 p-2 text-red-400 hover:bg-red-950" title="Delete">
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" onClick={() => setPreview(null)}>
          <div className="w-full max-w-3xl rounded-xl border border-zinc-700 bg-zinc-900 p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <p className="truncate font-medium text-white">{preview.title}</p>
              <button onClick={() => setPreview(null)} className="text-zinc-400 hover:text-white"><X size={20} /></button>
            </div>
            <video key={preview.id} controls autoPlay className="max-h-[60vh] w-full rounded bg-black" src={`${API}/api/clips/${preview.id}/stream`} />
          </div>
        </div>
      )}
    </div>
  );
}
