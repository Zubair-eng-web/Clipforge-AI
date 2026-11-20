"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useRef, useState } from "react";
import { Music, Trash2, Upload } from "lucide-react";
import Wave from "@/components/Wave";
import { API, api, fmtBytes, fmtDur } from "@/lib/api8";

export default function MusicLibraryPage() {
  const [tracks, setTracks] = useState<any[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [cols, setCols] = useState<any[]>([]);
  const [folder, setFolder] = useState("");
  const [colFilter, setColFilter] = useState(0);
  const [q, setQ] = useState("");
  const [upFolder, setUpFolder] = useState("");
  const [newCol, setNewCol] = useState("");
  const [waves, setWaves] = useState<Record<number, number[]>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const qs = `?folder=${encodeURIComponent(folder)}&q=${encodeURIComponent(q)}&collection_id=${colFilter}`;
      const d = await api("/api/music" + qs);
      setTracks(d.items);
      setFolders(d.folders);
      setCols((await api("/api/music-collections")).items);
    } catch (e: any) { setErr(e.message); }
  }, [folder, q, colFilter]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let dead = false;
    (async () => {
      for (const t of tracks) {
        if (dead) return;
        if (waves[t.id]) continue;
        try {
          const d = await api(`/api/music/${t.id}/waveform`);
          if (!dead) setWaves((w) => ({ ...w, [t.id]: d.peaks }));
        } catch { /* ignore */ }
      }
    })();
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracks]);

  async function upload(files: FileList | null) {
    if (!files || !files.length) return;
    setBusy(true); setErr(""); setMsg("");
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    fd.append("folder", upFolder);
    try {
      const r = await fetch(`${API}/api/music/upload`, { method: "POST", body: fd });
      const d = await r.json();
      setMsg(`${d.uploaded?.length ?? 0} track(s) added.` + (d.errors?.length ? ` ${d.errors.length} failed: ${d.errors.map((e: any) => e.filename + " (" + e.error + ")").join("; ")}` : ""));
      load();
    } catch { setErr("Upload failed. Is the backend running?"); }
    setBusy(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function patch(t: any, field: string, label: string) {
    const v = window.prompt(label, t[field] ?? "");
    if (v === null) return;
    try { await api("/api/music/" + t.id, { method: "PATCH", body: JSON.stringify({ [field]: v }) }); load(); }
    catch (e: any) { setErr(e.message); }
  }
  async function del(t: any) {
    if (!window.confirm(`Delete "${t.name}" from the library? Clips already made keep their music.`)) return;
    await api("/api/music/" + t.id, { method: "DELETE" });
    load();
  }
  async function createCol() {
    try { await api("/api/music-collections", { method: "POST", body: JSON.stringify({ name: newCol }) }); setNewCol(""); load(); }
    catch (e: any) { setErr(e.message); }
  }
  async function delCol(id: number) {
    if (!window.confirm("Delete this collection? Tracks stay in the library.")) return;
    await api("/api/music-collections/" + id, { method: "DELETE" });
    if (colFilter === id) setColFilter(0);
    load();
  }
  async function addToCol(t: any, cid: string) {
    if (!cid) return;
    await api(`/api/music-collections/${cid}/tracks`, { method: "POST", body: JSON.stringify({ track_ids: [t.id] }) });
    load();
  }

  const sel = "rounded bg-zinc-800 px-2 py-1 text-sm text-white";
  return (
    <div className="max-w-5xl space-y-5 text-zinc-200">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Music className="text-violet-400" size={24} /> Music Library</h1>
      <p className="text-sm text-zinc-400">Your own music, stored on this PC. Use only music you have the right to use. Nothing is downloaded automatically.</p>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <input ref={fileRef} type="file" multiple accept="audio/*,.mp3,.wav,.aac,.m4a,.flac,.ogg,.opus,.wma" onChange={(e) => upload(e.target.files)} disabled={busy} className="text-sm" />
        <input value={upFolder} onChange={(e) => setUpFolder(e.target.value)} placeholder="Folder name (optional)" className={sel} />
        <span className="flex items-center gap-1 text-xs text-zinc-500"><Upload size={14} /> {busy ? "Uploading..." : "MP3, WAV, AAC, M4A, FLAC and more"}</span>
      </div>
      {msg && <p className="text-sm text-green-400">{msg}</p>}
      {err && <p className="text-sm text-red-400">{err}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <select value={folder} onChange={(e) => setFolder(e.target.value)} className={sel}>
          <option value="">All folders</option>
          {folders.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <select value={colFilter} onChange={(e) => setColFilter(Number(e.target.value))} className={sel}>
          <option value={0}>All collections</option>
          {cols.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.track_count})</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name" className={sel} />
        <input value={newCol} onChange={(e) => setNewCol(e.target.value)} placeholder="New collection" className={sel} />
        <button onClick={createCol} disabled={!newCol.trim()} className="rounded bg-violet-600 px-3 py-1 text-sm text-white disabled:opacity-40">Create</button>
        {colFilter > 0 && <button onClick={() => delCol(colFilter)} className="text-xs text-red-400">Delete this collection</button>}
      </div>

      {tracks.length === 0 && <p className="text-zinc-500">No tracks yet. Upload some music above.</p>}
      <div className="space-y-3">
        {tracks.map((t) => (
          <div key={t.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-semibold text-white">{t.name}</p>
                <p className="text-xs text-zinc-500">{fmtDur(t.duration_sec)} | {fmtBytes(t.size_bytes)} | folder: {t.folder || "-"} | tags: {t.tags || "-"}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <button onClick={() => patch(t, "name", "Rename")} className="underline text-zinc-300">Rename</button>
                <button onClick={() => patch(t, "folder", "Folder")} className="underline text-zinc-300">Folder</button>
                <button onClick={() => patch(t, "tags", "Tags (e.g. epic, drums)")} className="underline text-zinc-300">Tags</button>
                <select value="" onChange={(e) => addToCol(t, e.target.value)} className={sel}>
                  <option value="">Add to collection...</option>
                  {cols.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <a href={`/audio-studio?track=${t.id}`} className="rounded bg-zinc-800 px-2 py-1 text-violet-300">Use in Audio Studio</a>
                <button onClick={() => del(t)} className="text-red-400" title="Delete"><Trash2 size={15} /></button>
              </div>
            </div>
            <div className="mt-2 h-12 rounded bg-zinc-950">{waves[t.id] ? <Wave peaks={waves[t.id]} /> : null}</div>
            <audio controls preload="none" className="mt-2 w-full" src={`${API}/api/music/${t.id}/stream`} />
          </div>
        ))}
      </div>
    </div>
  );
}