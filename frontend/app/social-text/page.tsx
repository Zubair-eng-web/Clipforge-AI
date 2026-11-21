"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Loader2, Sparkles, Trash2 } from "lucide-react";
import { api, rows } from "@/lib/api8";

type ClipRow = { id: number; title: string; status: string };
type Meta = { tones: string[]; platforms: Record<string, string> };
type Item = Record<string, string | number | boolean | null> & { id: number; approved: boolean };

const FIELDS: [string, string, boolean][] = [
  ["title", "Title", false], ["description", "Description", true], ["caption", "Caption", true],
  ["hashtags", "Hashtags", false], ["keywords", "Keywords", false], ["cta", "Call to action", false],
  ["pinned_comment", "Pinned comment", true],
];
const inp = "w-full rounded bg-slate-800 border border-slate-700 p-2 text-sm";

export default function SocialTextPage() {
  const [clips, setClips] = useState<ClipRow[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tone, setTone] = useState("viral");
  const [platform, setPlatform] = useState("general");
  const [notes, setNotes] = useState("");
  const [history, setHistory] = useState<Item[]>([]);
  const [cur, setCur] = useState<Item | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const loadHistory = useCallback(async (id: number) => {
    try { setHistory(rows(await api(`/api/social?clip_id=${id}`)) as Item[]); } catch { setHistory([]); }
  }, []);

  useEffect(() => {
    api("/api/clips?limit=500").then((d) => {
      const list = (rows(d) as ClipRow[]).filter((c) => c.status === "ready");
      setClips(list);
      if (list.length) setClipId(list[0].id);
    }).catch(() => setMsg("Backend not reachable. Start it with .\\scripts\\start-all.ps1"));
    api("/api/social/options").then((d) => setMeta(d as Meta)).catch(() => setMsg("Cannot load options."));
  }, []);

  useEffect(() => {
    setCur(null); setForm({}); setMsg("");
    if (clipId !== null) loadHistory(clipId);
  }, [clipId, loadHistory]);

  function open(it: Item) {
    setCur(it);
    setForm(Object.fromEntries(FIELDS.map(([k]) => [k, String(it[k] ?? "")])));
  }

  async function generate() {
    if (clipId === null) return;
    setBusy(true); setMsg("");
    try {
      const d = (await api("/api/social/generate", {
        method: "POST", body: JSON.stringify({ clip_id: clipId, tone, platform, notes }),
      })) as Item & { source: string; warning: string | null };
      open(d);
      setMsg(d.warning ? String(d.warning) : "Generated with Gemini from this clip's real data. Review and edit before use.");
      await loadHistory(clipId);
    } catch (e) { setMsg((e as Error).message); }
    setBusy(false);
  }

  async function save(approved?: boolean) {
    if (!cur) return;
    try {
      const body: Record<string, unknown> = { ...form };
      if (approved !== undefined) body.approved = approved;
      const d = (await api(`/api/social/${cur.id}`, { method: "PUT", body: JSON.stringify(body) })) as Item;
      setCur(d);
      setMsg(approved === undefined ? "Saved." : approved ? "Approved." : "Approval removed.");
      if (clipId !== null) await loadHistory(clipId);
    } catch (e) { setMsg((e as Error).message); }
  }

  async function remove(id: number) {
    try {
      await api(`/api/social/${id}`, { method: "DELETE" });
      if (cur?.id === id) { setCur(null); setForm({}); }
      if (clipId !== null) await loadHistory(clipId);
    } catch (e) { setMsg((e as Error).message); }
  }

  const copy = (t: string) => { navigator.clipboard.writeText(t).then(() => setMsg("Copied.")).catch(() => setMsg("Copy failed.")); };
  const all = FIELDS.map(([k, l]) => `${l}:\n${form[k] ?? ""}`).join("\n\n");

  return (
    <div className="p-6 space-y-5 max-w-6xl text-slate-200">
      <div className="flex items-center gap-3">
        <Sparkles className="w-7 h-7 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold">Social Text Generator</h1>
          <p className="text-sm text-slate-400">Title, description, caption, hashtags, keywords, CTA and pinned comment. Built only from the clip&apos;s real title, scene description and speech.</p>
        </div>
      </div>
      {msg && <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">{msg}</div>}

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="space-y-3">
          <label className="block text-sm">Clip
            <select className={inp + " mt-1"} value={clipId ?? ""} onChange={(e) => setClipId(Number(e.target.value))}>
              {clips.length === 0 && <option value="">No ready clips</option>}
              {clips.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.title}</option>)}
            </select>
          </label>
          <div className="text-sm">Tone
            <div className="mt-1 flex flex-wrap gap-2">
              {(meta?.tones ?? []).map((t) => (
                <button key={t} onClick={() => setTone(t)}
                  className={`rounded-full border px-3 py-1 text-xs capitalize ${tone === t ? "border-violet-500 bg-violet-500/20" : "border-slate-700"}`}>{t}</button>
              ))}
            </div>
          </div>
          <label className="block text-sm">Platform
            <select className={inp + " mt-1"} value={platform} onChange={(e) => setPlatform(e.target.value)}>
              {meta && Object.entries(meta.platforms).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label className="block text-sm">Your notes (optional, real facts only)
            <textarea className={inp + " mt-1"} rows={3} maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. 5-star chase on the bridge, no deaths" />
          </label>
          <p className="text-xs text-amber-400">With a Gemini key, the clip title, scene description and speech text are sent to Google Gemini (no video frames).</p>
          <button disabled={busy || clipId === null} onClick={generate}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-4 py-2 font-medium">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} Generate text
          </button>
          <div className="space-y-1 pt-2">
            <div className="text-sm font-semibold">Saved for this clip ({history.length})</div>
            {history.map((h) => (
              <div key={h.id} className={`flex items-center gap-2 rounded border p-2 text-xs ${cur?.id === h.id ? "border-violet-500" : "border-slate-700"}`}>
                <button className="flex-1 text-left truncate" onClick={() => open(h)}>{String(h.tone)}: {String(h.title) || "(no title)"}</button>
                {h.approved && <Check className="w-3 h-3 text-emerald-400" />}
                <button onClick={() => remove(h.id)} className="text-slate-500 hover:text-red-400"><Trash2 className="w-3 h-3" /></button>
              </div>
            ))}
          </div>
        </div>

        <div className="lg:col-span-2 space-y-3">
          {!cur && <p className="text-sm text-slate-400">Choose a clip and press &quot;Generate text&quot;, or open a saved one.</p>}
          {cur && (
            <>
              {FIELDS.map(([k, label, multi]) => (
                <div key={k}>
                  <div className="flex items-center justify-between text-sm">
                    <span>{label}</span>
                    <button className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200" onClick={() => copy(form[k] ?? "")}><Copy className="w-3 h-3" /> Copy</button>
                  </div>
                  {multi
                    ? <textarea className={inp} rows={3} value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
                    : <input className={inp} value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />}
                </div>
              ))}
              <div className="flex flex-wrap gap-3 pt-1">
                <button onClick={() => save()} className="rounded bg-slate-700 hover:bg-slate-600 px-3 py-1.5 text-sm">Save edits</button>
                <button onClick={() => save(!cur.approved)} className={`rounded px-3 py-1.5 text-sm ${cur.approved ? "bg-emerald-700" : "bg-violet-700 hover:bg-violet-600"}`}>
                  {cur.approved ? "Approved (click to undo)" : "Approve"}
                </button>
                <button onClick={() => copy(all)} className="rounded bg-slate-700 hover:bg-slate-600 px-3 py-1.5 text-sm">Copy all</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}