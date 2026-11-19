"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from "react";
import { api, rows } from "@/lib/api8";

export default function ProjectsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [videos, setVideos] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [videoId, setVideoId] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      setItems((await api("/api/projects")).items);
      setVideos(rows(await api("/api/videos")));
    } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create() {
    setErr("");
    try {
      await api("/api/projects", { method: "POST", body: JSON.stringify({ name, description: desc, video_id: videoId ? Number(videoId) : null }) });
      setName(""); setDesc(""); setVideoId("");
      load();
    } catch (e: any) { setErr(e.message); }
  }
  async function remove(id: number) {
    if (!confirm("Delete this project? Videos and clips are kept.")) return;
    await api("/api/projects/" + id, { method: "DELETE" });
    load();
  }

  return (
    <div className="p-6 space-y-6 text-zinc-200">
      <h1 className="text-2xl font-bold text-white">My Projects</h1>
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3 max-w-xl">
        <input className="w-full rounded bg-zinc-800 px-3 py-2" placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} />
        <textarea className="w-full rounded bg-zinc-800 px-3 py-2" placeholder="Notes (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <select className="w-full rounded bg-zinc-800 px-3 py-2" value={videoId} onChange={(e) => setVideoId(e.target.value)}>
          <option value="">No video linked</option>
          {videos.map((v) => <option key={v.id} value={v.id}>{v.original_name ?? v.name ?? "Video " + v.id}</option>)}
        </select>
        <button disabled={!name.trim()} onClick={create} className="rounded bg-violet-600 px-4 py-2 text-white disabled:opacity-40">Create project</button>
        {err && <p className="text-red-400 text-sm">{err}</p>}
      </div>
      {items.length === 0 && <p className="text-zinc-500">No projects yet.</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((p) => (
          <div key={p.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="flex justify-between"><h2 className="font-semibold text-white">{p.name}</h2>
              <button onClick={() => remove(p.id)} className="text-xs text-red-400">Delete</button></div>
            {p.description && <p className="mt-1 text-sm text-zinc-400">{p.description}</p>}
            <p className="mt-2 text-xs text-zinc-500">Video: {p.video_name ?? "none"} | Clips: {p.clip_count}</p>
          </div>
        ))}
      </div>
    </div>
  );
}