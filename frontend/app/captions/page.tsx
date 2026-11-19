"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2, Play, Type, Wand2 } from "lucide-react";
import { API, fmtClock, watchJob, type ClipItem } from "@/lib/api";

type CapLine = { start: number; end: number; text: string; has_words?: boolean };
type CapStyle = "classic" | "bold" | "highlight";
type CapPosition = "bottom" | "center" | "top";

export default function SmartCaptionsPage() {
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [lines, setLines] = useState<CapLine[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [language, setLanguage] = useState("auto");
  const [style, setStyle] = useState<CapStyle>("classic");
  const [position, setPosition] = useState<CapPosition>("bottom");
  const [progress, setProgress] = useState<number | null>(null);
  const [stage, setStage] = useState("");
  const [msg, setMsg] = useState("");
  const [result, setResult] = useState<ClipItem | null>(null);
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    fetch(`${API}/api/clips?limit=200`)
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then((d: { items: ClipItem[] }) => {
        const ready = d.items.filter((c) => c.status === "ready");
        setClips(ready);
        if (ready.length) setClipId(ready[0].id);
      })
      .catch(() => setMsg("Cannot reach the backend. Start it with .\\scripts\\start-all.ps1"));
    return () => stopRef.current?.();
  }, []);

  const loadCaptions = useCallback(async (id: number) => {
    try {
      const r = await fetch(`${API}/api/clips/${id}/captions`);
      if (!r.ok) {
        setLines([]);
        setLoaded(false);
        return;
      }
      const d = (await r.json()) as { lines: CapLine[] };
      setLines(d.lines);
      setLoaded(true);
      setDirty(false);
    } catch {
      setLines([]);
      setLoaded(false);
    }
  }, []);

  useEffect(() => {
    stopRef.current?.();
    stopRef.current = null;
    setProgress(null);
    setStage("");
    setMsg("");
    setResult(null);
    setLines([]);
    setLoaded(false);
    setDirty(false);
    if (clipId !== null) loadCaptions(clipId);
  }, [clipId, loadCaptions]);

  function track(jobId: number, label: string, onDone: () => void) {
    setStage(label);
    setProgress(0);
    stopRef.current = watchJob(jobId, (j) => {
      setProgress(j.progress);
      if (["completed", "failed", "cancelled"].includes(j.status)) {
        setProgress(null);
        setStage("");
        if (j.status === "completed") onDone();
        else setMsg(j.error || `Job ${j.status}`);
      }
    });
  }

  async function post(path: string, body: unknown) {
    const r = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${r.status})`);
    return data;
  }

  async function generate() {
    if (clipId === null) return;
    const id = clipId;
    setMsg("");
    setResult(null);
    try {
      const d = await post(`/api/clips/${id}/captions/generate`, { language: language === "auto" ? null : language });
      track(d.job_id, "Transcribing the clip (word by word)...", () => loadCaptions(id));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not start.");
    }
  }

  async function save(): Promise<boolean> {
    if (clipId === null) return false;
    const r = await fetch(`${API}/api/clips/${clipId}/captions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines: lines.map((l) => ({ start: l.start, end: l.end, text: l.text })) }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setMsg(typeof data.detail === "string" ? data.detail : "Could not save the captions.");
      return false;
    }
    setDirty(false);
    return true;
  }

  async function burn() {
    if (clipId === null) return;
    const id = clipId;
    setMsg("");
    setResult(null);
    try {
      if (dirty && !(await save())) return;
      const d = await post(`/api/clips/${id}/captions/burn`, { style, position });
      track(d.job_id, "Burning captions into the video...", () => {
        fetch(`${API}/api/clips/${d.clip_id}`)
          .then((r) => r.json())
          .then((c: ClipItem) => setResult(c))
          .catch(() => setMsg("Captioned clip created. Open Generated Clips."));
      });
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not start.");
    }
  }

  function editText(i: number, value: string) {
    setLines((prev) => prev.map((l, idx) => (idx === i ? { ...l, text: value } : l)));
    setDirty(true);
  }

  function removeLine(i: number) {
    setLines((prev) => prev.filter((_, idx) => idx !== i));
    setDirty(true);
  }

  const busy = progress !== null;
  const clip = clips.find((c) => c.id === clipId) ?? null;

  return (
    <div className="max-w-4xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
        <Type className="text-violet-400" size={24} /> Smart Captions
      </h1>
      <p className="text-sm text-zinc-400">
        Pick a generated clip, create captions from its speech, fix any word, then burn them into the video or download an SRT file.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <select
          value={clipId ?? ""}
          onChange={(e) => setClipId(e.target.value ? Number(e.target.value) : null)}
          className="min-w-64 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
        >
          {clips.length === 0 && <option value="">No ready clips yet</option>}
          {clips.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
          title="Spoken language"
        >
          <option value="auto">Auto-detect language</option>
          <option value="en">English</option>
          <option value="ur">Urdu</option>
          <option value="hi">Hindi</option>
          <option value="ar">Arabic</option>
        </select>
        <button
          onClick={generate}
          disabled={clipId === null || busy}
          className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
          {loaded ? "Generate again" : "Generate captions"}
        </button>
      </div>

      {busy && (
        <div className="mt-4">
          <div className="h-2 w-full overflow-hidden rounded bg-zinc-800">
            <div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(progress ?? 0, 100)}%` }} />
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            {stage} {Math.round(progress ?? 0)}%
          </p>
        </div>
      )}

      {msg && <p className="mt-4 rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}

      {clip && (
        <video
          key={clip.id}
          controls
          className="mt-6 max-h-72 w-full rounded-xl bg-black"
          src={`${API}/api/clips/${clip.id}/stream`}
        />
      )}

      {clip && !loaded && !busy && (
        <p className="mt-6 rounded-xl border border-dashed border-zinc-700 p-8 text-center text-sm text-zinc-400">
          No captions yet. Press <b>Generate captions</b>. The first run downloads or loads the Whisper model.
        </p>
      )}

      {loaded && lines.length === 0 && (
        <p className="mt-6 rounded-xl border border-dashed border-zinc-700 p-8 text-center text-sm text-zinc-400">
          No speech was found in this clip.
        </p>
      )}

      {loaded && lines.length > 0 && (
        <>
          <div className="mt-6 space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-2">
                <span className="w-28 shrink-0 text-xs text-zinc-500">
                  {fmtClock(l.start)} - {fmtClock(l.end)}
                </span>
                <input
                  value={l.text}
                  onChange={(e) => editText(i, e.target.value)}
                  className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-white"
                />
                <button onClick={() => removeLine(i)} className="text-xs text-red-400 hover:underline">
                  Remove
                </button>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={save}
              disabled={!dirty || busy}
              className="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-white hover:bg-zinc-700 disabled:opacity-40"
            >
              Save changes
            </button>
            <a
              href={`${API}/api/clips/${clipId}/captions.srt`}
              className="inline-flex items-center gap-1 rounded-lg bg-zinc-800 px-4 py-2 text-sm text-white hover:bg-zinc-700"
            >
              <Download size={15} /> SRT file
            </a>
            <select
              value={style}
              onChange={(e) => setStyle(e.target.value as CapStyle)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
            >
              <option value="classic">Classic (white)</option>
              <option value="bold">Bold (yellow)</option>
              <option value="highlight">Highlight (word by word)</option>
            </select>
            <select
              value={position}
              onChange={(e) => setPosition(e.target.value as CapPosition)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
            >
              <option value="bottom">Bottom</option>
              <option value="center">Center</option>
              <option value="top">Top</option>
            </select>
            <button
              onClick={burn}
              disabled={busy}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              Burn into video
            </button>
          </div>
        </>
      )}

      {result && (
        <div className="mt-6 rounded-xl border border-emerald-900 bg-emerald-950/30 p-4">
          <p className="font-medium text-white">{result.title}</p>
          <p className="text-xs text-zinc-400">Saved in Generated Clips.</p>
          <video
            key={result.id}
            controls
            className="mt-3 max-h-72 w-full rounded bg-black"
            src={`${API}/api/clips/${result.id}/stream`}
          />
          <div className="mt-3 flex gap-3 text-sm">
            <a className="inline-flex items-center gap-1 underline" href={`${API}/api/clips/${result.id}/stream`} target="_blank" rel="noreferrer">
              <Play size={14} /> Open
            </a>
            <a className="inline-flex items-center gap-1 underline" href={`${API}/api/clips/${result.id}/download`}>
              <Download size={14} /> Download
            </a>
          </div>
        </div>
      )}
    </div>
  );
}