"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Search, Trash2, Play, X, Film, Music, Scissors } from "lucide-react";
import { API, fmtBytes, fmtDuration, type VideoItem } from "@/lib/api";

export default function LibraryPage() {
  const [items, setItems] = useState<VideoItem[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<VideoItem | null>(null);

  const load = useCallback(async (query: string) => {
    try {
      const r = await fetch(`${API}/api/videos?q=${encodeURIComponent(query)}`);
      if (!r.ok) throw new Error();
      const d = await r.json();
      setItems(d.items);
      setTotal(d.total);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(q), 250);
    return () => clearTimeout(t);
  }, [q, load]);

  async function remove(v: VideoItem) {
    if (!window.confirm(`Permanently delete "${v.name}" from your computer?\nThis cannot be undone.`)) return;
    const r = await fetch(`${API}/api/videos/${v.id}`, { method: "DELETE" });
    if (r.ok) {
      if (preview?.id === v.id) setPreview(null);
      load(q);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Video Library</h1>
          <p className="text-sm text-zinc-400">{total} file{total === 1 ? "" : "s"} saved locally</p>
        </div>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-2.5 text-zinc-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name..."
            className="w-64 rounded-lg border border-zinc-700 bg-zinc-900 py-2 pl-9 pr-3 text-sm text-white placeholder-zinc-500 outline-none focus:border-violet-500"
          />
        </div>
      </div>

      {error && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Duration</th>
              <th className="px-4 py-3">Resolution</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((v) => (
              <tr key={v.id} className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/40">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 text-white">
                    {v.has_video ? <Film size={16} className="text-violet-400" /> : <Music size={16} className="text-sky-400" />}
                    <span className="max-w-xs truncate">{v.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-zinc-300">{fmtDuration(v.duration_sec)}</td>
                <td className="px-4 py-3 text-zinc-300">{v.width ? `${v.width}x${v.height}` : "audio"}</td>
                <td className="px-4 py-3 text-zinc-300">{fmtBytes(v.size_bytes)}</td>
                <td className="px-4 py-3 text-zinc-400">{new Date(v.created_at).toLocaleString()}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    {v.has_video && (
                      <Link href={`/manual-clipper?video=${v.id}`} className="rounded-md bg-zinc-800 p-2 text-violet-300 hover:bg-zinc-700" title="Clip this video">
                        <Scissors size={15} />
                      </Link>
                    )}
                    <button onClick={() => setPreview(v)} className="rounded-md bg-zinc-800 p-2 hover:bg-zinc-700" title="Preview">
                      <Play size={15} />
                    </button>
                    <button onClick={() => remove(v)} className="rounded-md bg-zinc-800 p-2 text-red-400 hover:bg-red-950" title="Delete">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && items.length === 0 && !error && (
          <p className="p-8 text-center text-sm text-zinc-500">
            {q ? "No files match your search." : "No files yet. Go to Upload Videos to add some."}
          </p>
        )}
      </div>

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" onClick={() => setPreview(null)}>
          <div className="w-full max-w-3xl rounded-xl border border-zinc-700 bg-zinc-900 p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <p className="truncate font-medium text-white">{preview.name}</p>
              <button onClick={() => setPreview(null)} className="text-zinc-400 hover:text-white"><X size={20} /></button>
            </div>
            {preview.has_video ? (
              <video key={preview.id} controls autoPlay className="max-h-[60vh] w-full rounded bg-black" src={`${API}/api/videos/${preview.id}/stream`} />
            ) : (
              <audio key={preview.id} controls autoPlay className="w-full" src={`${API}/api/videos/${preview.id}/stream`} />
            )}
            <p className="mt-3 text-xs text-zinc-500">
              If a MOV/MKV/AVI file does not play here, it is still saved correctly. Browser preview for those formats improves in Phase 3.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}