"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { API, fmtBytes } from "@/lib/api";

type Folder = { name: string; bytes: number; files: number };
type SettingsData = {
  python: string;
  max_concurrent_jobs: number;
  ai: { gemini_key_set: boolean; whisper_model: string; whisper_language: string };
  tools: Record<string, boolean>;
  storage: { path: string; used_bytes: number; free_bytes: number; total_bytes: number; folders: Folder[] };
  system: { ram_percent: number; ram_total_bytes: number };
};

const TOOL_LABELS: Record<string, string> = {
  ffmpeg: "FFmpeg", ffprobe: "FFprobe", libass: "Subtitles support (libass)", opencv: "OpenCV",
  faster_whisper: "faster-whisper", scenedetect: "PySceneDetect", yt_dlp: "yt-dlp",
};

function Pill({ ok, yes = "OK", no = "Missing" }: { ok: boolean; yes?: string; no?: string }) {
  return ok ? (
    <span className="flex items-center gap-1 text-emerald-400"><CheckCircle2 size={15} /> {yes}</span>
  ) : (
    <span className="flex items-center gap-1 text-red-400"><XCircle size={15} /> {no}</span>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-zinc-800/60 py-2 text-sm last:border-0">
      <span className="text-zinc-400">{label}</span>
      <span className="text-zinc-200">{children}</span>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
      <h2 className="mb-2 font-semibold text-white">{title}</h2>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const [d, setD] = useState<SettingsData | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/settings`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setD)
      .catch(() => setOffline(true));
  }, []);

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-white">Settings</h1>
      <p className="text-sm text-zinc-400">Live status of this computer. To change a value, edit the <code>.env</code> file and restart with <code>.\scripts\start-all.ps1</code>.</p>

      {offline && (
        <div className="mt-6 rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          Backend is offline. Start it with <code>.\scripts\start-all.ps1</code>
        </div>
      )}

      {d && (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card title="Processing">
            <Row label="Max concurrent jobs (MAX_CONCURRENT_JOBS)">{d.max_concurrent_jobs}</Row>
            <Row label="RAM in use">{Math.round(d.system.ram_percent)}% of {fmtBytes(d.system.ram_total_bytes)}</Row>
            <Row label="Python">{d.python}</Row>
          </Card>

          <Card title="AI">
            <Row label="Gemini API key (GEMINI_API_KEY)"><Pill ok={d.ai.gemini_key_set} yes="Set" no="Not set (local scoring is used)" /></Row>
            <Row label="Whisper model">{d.ai.whisper_model}</Row>
            <Row label="Whisper language">{d.ai.whisper_language}</Row>
          </Card>

          <Card title="Tools">
            {Object.entries(d.tools).map(([k, v]) => (
              <Row key={k} label={TOOL_LABELS[k] ?? k}><Pill ok={v} /></Row>
            ))}
          </Card>

          <Card title="Storage">
            <Row label="Location"><span className="break-all text-xs">{d.storage.path}</span></Row>
            <Row label="Used by ClipForge">{fmtBytes(d.storage.used_bytes)}</Row>
            <Row label="Free on disk">{fmtBytes(d.storage.free_bytes)}</Row>
            <div className="mt-3 space-y-1">
              {d.storage.folders.map((f) => (
                <div key={f.name} className="flex justify-between text-xs text-zinc-500">
                  <span>{f.name}</span>
                  <span>{f.files} files | {fmtBytes(f.bytes)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}