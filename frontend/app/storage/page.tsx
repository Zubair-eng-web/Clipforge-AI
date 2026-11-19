"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from "react";
import { api, fmtBytes } from "@/lib/api8";

export default function StoragePage() {
  const [d, setD] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setD(await api("/api/storage-manager/overview")); } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function clean(target: string, label: string) {
    if (!confirm(`${label}?`)) return;
    setErr(""); setMsg("");
    try {
      const r = await api("/api/storage-manager/cleanup", { method: "POST", body: JSON.stringify({ target }) });
      setMsg(`Done: ${r.files_or_items} items, freed ${fmtBytes(r.freed_bytes)}`);
      load();
    } catch (e: any) { setErr(e.message); }
  }
  if (!d) return <div className="p-6 text-zinc-400">{err || "Loading..."}</div>;
  const max = Math.max(...d.folders.map((f: any) => f.bytes), 1);
  const actions = [
    ["previews", "Clear browser previews (regenerated when needed)", fmtBytes(d.previews_bytes)],
    ["temporary", "Clear temporary folder", fmtBytes(d.temporary_bytes)],
    ["orphans", "Delete files not used by any clip, thumbnail or video", `${d.orphan_files} files, ${fmtBytes(d.orphan_bytes)}`],
    ["failed_clips", "Delete failed and cancelled clips", `${d.failed_clips} clips`],
  ];
  return (
    <div className="p-6 space-y-6 text-zinc-200">
      <h1 className="text-2xl font-bold text-white">Storage Manager</h1>
      <div className="flex flex-wrap gap-3 text-sm">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2">App storage: <b>{fmtBytes(d.total_bytes)}</b></div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2">Database: <b>{fmtBytes(d.db_bytes)}</b></div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2">Disk free: <b>{fmtBytes(d.disk.free)}</b> of {fmtBytes(d.disk.total)}</div>
      </div>
      {msg && <p className="text-green-400 text-sm">{msg}</p>}
      {err && <p className="text-red-400 text-sm">{err}</p>}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-2">
        {d.folders.map((f: any) => (
          <div key={f.name} className="flex items-center gap-3 text-sm">
            <span className="w-40">{f.name}</span>
            <div className="flex-1 h-2 rounded bg-zinc-800"><div className="h-2 rounded bg-violet-500" style={{ width: `${(f.bytes / max) * 100}%` }} /></div>
            <span className="w-24 text-right text-zinc-400">{fmtBytes(f.bytes)}</span>
          </div>
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {actions.map(([t, label, info]) => (
          <div key={t} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <p className="text-sm">{label}</p><p className="text-xs text-zinc-500 mb-2">{info}</p>
            <button onClick={() => clean(t, label)} className="rounded bg-zinc-800 px-3 py-1 text-sm hover:bg-zinc-700">Run</button>
          </div>
        ))}
      </div>
      <p className="text-xs text-zinc-500">Original videos and ready clips are never touched by these actions.</p>
    </div>
  );
}