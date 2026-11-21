"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Loader2, Trash2, Video } from "lucide-react";
import { API, api, rows, fmtDur } from "@/lib/api8";

type Clip = { id: number; title: string; status: string; duration_sec: number | null };
const PAGE = 12;

export default function ClipsGalleryPage() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(PAGE);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [broken, setBroken] = useState<Set<number>>(new Set());
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const list = (rows(await api("/api/clips?limit=1000")) as Clip[]).filter((c) => c.status === "ready");
      list.sort((a, b) => b.id - a.id);
      setClips(list);
    } catch {
      setMsg("Backend not reachable. Start it with .\\scripts\\start-all.ps1");
    }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const visible = useMemo(
    () => clips.filter((c) => !broken.has(c.id) && (c.title || "").toLowerCase().includes(q.toLowerCase())),
    [clips, broken, q],
  );
  const page = visible.slice(0, shown);
  const brokenClips = clips.filter((c) => broken.has(c.id));

  async function remove(ids: number[], ask: string) {
    if (!ids.length || !window.confirm(ask)) return;
    setBusy(true); setMsg("");
    let fail = 0;
    for (const id of ids) {
      try { await api(`/api/clips/${id}`, { method: "DELETE" }); } catch { fail++; }
    }
    setSel(new Set());
    setBroken((b) => { const n = new Set(b); ids.forEach((i) => n.delete(i)); return n; });
    await load();
    setMsg(fail ? `${ids.length - fail} deleted, ${fail} failed.` : `${ids.length} clip(s) deleted.`);
    setBusy(false);
  }

  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const selectShown = () => setSel(new Set(page.map((c) => c.id)));

  return (
    <div className="p-6 space-y-5 max-w-7xl text-slate-200">
      <div className="flex items-center gap-3">
        <Video className="w-7 h-7 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold">Clips Gallery</h1>
          <p className="text-sm text-slate-400">All your finished clips as playable videos. Only ready clips are shown. Delete removes the clip from your library.</p>
        </div>
      </div>

      {msg && <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">{msg}</div>}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input value={q} onChange={(e) => { setQ(e.target.value); setShown(PAGE); }} placeholder="Search by title"
          className="rounded bg-slate-800 border border-slate-700 p-2 w-64" />
        <span className="text-slate-400">{visible.length} clip(s)</span>
        <button onClick={selectShown} className="rounded bg-slate-700 hover:bg-slate-600 px-3 py-1.5">Select shown</button>
        {sel.size > 0 && (
          <>
            <button onClick={() => setSel(new Set())} className="rounded bg-slate-700 hover:bg-slate-600 px-3 py-1.5">Clear ({sel.size})</button>
            <button disabled={busy} onClick={() => remove(Array.from(sel), `Delete ${sel.size} selected clip(s)?`)}
              className="inline-flex items-center gap-1 rounded bg-red-700 hover:bg-red-600 disabled:opacity-50 px-3 py-1.5">
              <Trash2 className="w-4 h-4" /> Delete selected
            </button>
          </>
        )}
      </div>

      {brokenClips.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-600/50 bg-amber-500/10 px-4 py-2 text-sm">
          <span>{brokenClips.length} broken clip(s) (file missing or not playable) are hidden.</span>
          <button disabled={busy} onClick={() => remove(brokenClips.map((c) => c.id), `Delete ${brokenClips.length} broken clip(s)?`)}
            className="rounded bg-amber-700 hover:bg-amber-600 disabled:opacity-50 px-3 py-1">Delete broken</button>
        </div>
      )}

      {loading && <div className="flex items-center gap-2 text-sm text-slate-400"><Loader2 className="w-4 h-4 animate-spin" /> Loading...</div>}
      {!loading && visible.length === 0 && <p className="text-sm text-slate-400">No clips yet. Make one in Manual Clipper, AI Auto Clipper or Gaming Highlights.</p>}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {page.map((c) => (
          <div key={c.id} className={`rounded-xl border p-2 space-y-2 bg-slate-900/50 ${sel.has(c.id) ? "border-violet-500" : "border-slate-700"}`}>
            <video controls preload="metadata" className="w-full rounded-lg bg-black max-h-[280px]"
              poster={`${API}/api/clips/${c.id}/thumbnail`} src={`${API}/api/clips/${c.id}/stream`}
              onError={() => setBroken((b) => new Set(b).add(c.id))} />
            <div className="px-1 text-sm">
              <div className="truncate font-medium" title={c.title}>{c.title || "(no title)"}</div>
              <div className="text-xs text-slate-400">#{c.id} · {fmtDur(c.duration_sec)}</div>
            </div>
            <div className="flex items-center justify-between px-1 pb-1 text-xs">
              <label className="flex items-center gap-1"><input type="checkbox" checked={sel.has(c.id)} onChange={() => toggle(c.id)} /> Select</label>
              <div className="flex items-center gap-3">
                <a className="inline-flex items-center gap-1 text-slate-300 hover:text-white" href={`${API}/api/clips/${c.id}/download`}><Download className="w-3 h-3" /> Download</a>
                
                <button disabled={busy} onClick={() => remove([c.id], `Delete clip #${c.id} "${c.title}"?`)}
                  className="inline-flex items-center gap-1 text-red-400 hover:text-red-300 disabled:opacity-50"><Trash2 className="w-3 h-3" /> Delete</button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {visible.length > shown && (
        <button onClick={() => setShown(shown + PAGE)} className="rounded-lg border border-slate-600 hover:bg-slate-800 px-4 py-2 text-sm">
          Show more ({visible.length - shown} left)
        </button>
      )}
    </div>
  );
}

