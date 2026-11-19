"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from "react";
import { API, api, fmtDur, rows } from "@/lib/api8";

export default function CollectionsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState<any>(null);
  const [allClips, setAllClips] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [pick, setPick] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setItems((await api("/api/collections")).items); } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function openC(id: number) {
    setOpen(await api("/api/collections/" + id));
    setAllClips(rows(await api("/api/clips")).filter((c: any) => c.status === "ready"));
  }
  async function create() {
    try { await api("/api/collections", { method: "POST", body: JSON.stringify({ name }) }); setName(""); load(); }
    catch (e: any) { setErr(e.message); }
  }
  async function del(id: number) {
    if (!confirm("Delete this collection? Clips are kept.")) return;
    await api("/api/collections/" + id, { method: "DELETE" });
    if (open?.id === id) setOpen(null);
    load();
  }
  async function add() {
    if (!pick || !open) return;
    await api(`/api/collections/${open.id}/clips`, { method: "POST", body: JSON.stringify({ clip_ids: [Number(pick)] }) });
    setPick(""); openC(open.id); load();
  }
  async function removeClip(clipId: number) {
    await api(`/api/collections/${open.id}/clips/${clipId}`, { method: "DELETE" });
    openC(open.id); load();
  }

  return (
    <div className="p-6 space-y-6 text-zinc-200">
      <h1 className="text-2xl font-bold text-white">Collections</h1>
      <div className="flex gap-2 max-w-xl">
        <input className="flex-1 rounded bg-zinc-800 px-3 py-2" placeholder="New collection name" value={name} onChange={(e) => setName(e.target.value)} />
        <button disabled={!name.trim()} onClick={create} className="rounded bg-violet-600 px-4 py-2 text-white disabled:opacity-40">Create</button>
      </div>
      {err && <p className="text-red-400 text-sm">{err}</p>}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-2">
          {items.length === 0 && <p className="text-zinc-500">No collections yet.</p>}
          {items.map((c) => (
            <div key={c.id} className={`rounded-xl border p-3 cursor-pointer ${open?.id === c.id ? "border-violet-500" : "border-zinc-800"} bg-zinc-900/60`} onClick={() => openC(c.id)}>
              <div className="flex justify-between"><span className="font-semibold text-white">{c.name}</span>
                <button onClick={(e) => { e.stopPropagation(); del(c.id); }} className="text-xs text-red-400">Delete</button></div>
              <p className="text-xs text-zinc-500">{c.clip_count} clips</p>
            </div>
          ))}
        </div>
        <div className="lg:col-span-2">
          {!open ? <p className="text-zinc-500">Select a collection.</p> : (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">{open.name}</h2>
              <div className="flex gap-2">
                <select className="flex-1 rounded bg-zinc-800 px-3 py-2" value={pick} onChange={(e) => setPick(e.target.value)}>
                  <option value="">Add a ready clip...</option>
                  {allClips.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
                </select>
                <button onClick={add} className="rounded bg-violet-600 px-4 py-2 text-white">Add</button>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {open.clips.map((c: any) => (
                  <div key={c.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
                    {c.status === "ready" && <video className="w-full rounded mb-2" controls preload="metadata" src={`${API}/api/clips/${c.id}/stream`} />}
                    <div className="flex justify-between text-sm"><span>{c.title} ({fmtDur(c.duration_sec)})</span>
                      <button onClick={() => removeClip(c.id)} className="text-xs text-red-400">Remove</button></div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}