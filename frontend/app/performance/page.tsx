"use client";
import { useCallback, useEffect, useState } from "react";
import { Loader2, Zap } from "lucide-react";
import { API, fmtBytes } from "@/lib/api";

type Info = {
  settings: { low_memory: boolean; frame_width: number };
  effective: Record<string, string | null>;
  ram: { total_gb: number; available_gb: number; used_percent: number };
  recommend_low_memory: boolean;
  stale_temporary_bytes: number;
  music_peaks_bytes: number;
};

export default function PerformancePage() {
  const [info, setInfo] = useState<Info | null>(null);
  const [low, setLow] = useState(false);
  const [width, setWidth] = useState(384);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/performance`);
      if (!r.ok) throw new Error();
      const d = (await r.json()) as Info;
      setInfo(d);
      setLow(d.settings.low_memory);
      setWidth(d.settings.frame_width);
      setOffline(false);
    } catch { setOffline(true); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save() {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${API}/api/performance`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ low_memory: low, frame_width: width }),
      });
      setMsg(r.ok ? "Saved. It is active now, no restart needed." : "Could not save.");
      load();
    } catch { setMsg("Cannot reach the backend. Is it running?"); }
    finally { setBusy(false); }
  }

  async function clean(target: string) {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${API}/api/performance/cleanup`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target }),
      });
      const d = await r.json().catch(() => ({}));
      setMsg(r.ok ? `Removed ${d.files} file(s), freed ${fmtBytes(d.freed_bytes ?? 0)}.` : "Cleanup failed.");
      load();
    } catch { setMsg("Cannot reach the backend. Is it running?"); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Zap size={24} className="text-violet-400" /> Performance</h1>
      <p className="text-sm text-zinc-400">Settings for a PC with little RAM. Changes apply at once. Original videos and ready clips are never touched here.</p>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}

      {info && (
        <div className="mt-6 space-y-6">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 text-sm text-zinc-300">
            RAM: {info.ram.total_gb} GB total, {info.ram.available_gb} GB free ({info.ram.used_percent}% used).
            {info.recommend_low_memory && (
              <p className="mt-2 text-amber-300">This PC has about 8 GB of RAM. Turn on Low-memory mode below to keep analysis from running out of memory.</p>
            )}
          </div>

          <div className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <label className="flex items-center gap-2 text-sm font-medium text-white">
              <input type="checkbox" checked={low} onChange={(e) => setLow(e.target.checked)} /> Low-memory mode
            </label>
            <p className="text-xs text-zinc-500">Whisper uses the smaller &quot;base&quot; model (faster, a little less accurate), Gemini gets smaller batches, long videos use fewer analysis units, frames are 256 px.</p>
            <div>
              <p className="mb-1 text-xs text-zinc-400">Analysis frame size (Scene Detection and Gaming Highlights)</p>
              <select value={low ? 256 : width} disabled={low} onChange={(e) => setWidth(Number(e.target.value))}
                className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white disabled:opacity-50">
                <option value={256}>256 px (lowest RAM)</option>
                <option value={320}>320 px</option>
                <option value={384}>384 px (default)</option>
                <option value={512}>512 px (more detail, more data sent to Gemini)</option>
              </select>
            </div>
            <button onClick={save} disabled={busy}
              className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
              {busy && <Loader2 size={16} className="animate-spin" />} Save
            </button>
            <p className="text-xs text-zinc-500">
              Now in use: Whisper {info.effective.WHISPER_MODEL ?? "small (default)"}, batch {info.effective.SCENE_AI_BATCH ?? "8"}, max units {info.effective.SCENE_AI_MAX_UNITS ?? "150"}, frame {info.effective.FRAME_WIDTH ?? "384"} px.
            </p>
          </div>

          <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <h2 className="font-semibold text-white">Safe cleanup</h2>
            <div className="flex items-center justify-between text-sm text-zinc-300">
              <span>Old temporary files (older than 6 hours): {fmtBytes(info.stale_temporary_bytes)}</span>
              <button onClick={() => clean("stale_temporary")} disabled={busy} className="rounded-md bg-zinc-800 px-3 py-1 text-xs hover:bg-zinc-700 disabled:opacity-50">Clean</button>
            </div>
            <div className="flex items-center justify-between text-sm text-zinc-300">
              <span>Waveform cache (rebuilt when needed): {fmtBytes(info.music_peaks_bytes)}</span>
              <button onClick={() => clean("music_peaks")} disabled={busy} className="rounded-md bg-zinc-800 px-3 py-1 text-xs hover:bg-zinc-700 disabled:opacity-50">Clean</button>
            </div>
            <p className="text-xs text-zinc-500">Files of a job that is running right now are new, so they are not removed. Old temporary files are also cleaned at every server start. More options: Storage Manager.</p>
          </div>
        </div>
      )}
      {msg && <p className="mt-4 rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}
    </div>
  );
}