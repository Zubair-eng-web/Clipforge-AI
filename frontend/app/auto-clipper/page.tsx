"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Loader2, Play, Sparkles, Wand2 } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type VideoItem = { id: number; name: string };
type ClipItem = {
  id: number;
  title: string;
  start_sec: number;
  end_sec: number;
  status: string;
  ai_score?: number | null;
};

function asList(d: any): any[] {
  if (Array.isArray(d)) return d;
  return d?.items ?? d?.clips ?? d?.videos ?? [];
}

function fmt(sec: number) {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

async function api(path: string, init?: RequestInit) {
  const r = await fetch(`${API}${path}`, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `Request failed (${r.status})`);
  return data;
}

export default function AutoClipperPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState("none");
  const [highlightCount, setHighlightCount] = useState(0);
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const [count, setCount] = useState(5);
  const [mode, setMode] = useState<"accurate" | "fast">("accurate");
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/videos")
      .then((d) => {
        const list = asList(d).map((v: any) => ({
          id: v.id,
          name: v.original_name ?? v.name ?? v.title ?? `Video ${v.id}`,
        }));
        setVideos(list);
        if (list.length) setVideoId(list[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  const loadAnalysis = useCallback(async (id: number) => {
    try {
      const a = await api(`/api/videos/${id}/analysis?include_transcript=false`);
      setAnalysisStatus(a.status || "none");
      setHighlightCount((a.highlights || []).length);
      setSource(a.scoring_source || "");
      setNote(a.note || "");
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const loadClips = useCallback(async (id: number) => {
    try {
      const d = await api(`/api/clips?video_id=${id}`);
      setClips(asList(d));
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (videoId == null) return;
    setError("");
    loadAnalysis(videoId);
    loadClips(videoId);
  }, [videoId, loadAnalysis, loadClips]);

  useEffect(() => {
    if (videoId == null) return;
    const active = clips.some((c) => c.status === "pending" || c.status === "processing");
    if (!active) return;
    const t = setInterval(() => loadClips(videoId), 2000);
    return () => clearInterval(t);
  }, [clips, videoId, loadClips]);

  async function analyze() {
    if (videoId == null) return;
    setError("");
    setBusy("Analyzing (transcript, scenes, scoring)... this can take a few minutes on CPU");
    try {
      const { job_id } = await api(`/api/videos/${videoId}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      for (;;) {
        await new Promise((r) => setTimeout(r, 3000));
        const j = await api(`/api/jobs/${job_id}`);
        if (j.status === "completed") break;
        if (j.status === "failed" || j.status === "cancelled") {
          throw new Error(j.error || `Analysis ${j.status}`);
        }
        setBusy(`Analyzing... ${Math.round(j.progress ?? 0)}%`);
      }
      await loadAnalysis(videoId);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  async function generate() {
    if (videoId == null) return;
    setError("");
    setBusy("Creating clips...");
    try {
      await api(`/api/videos/${videoId}/auto-clips`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count, mode }),
      });
      await loadClips(videoId);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  const ready = analysisStatus === "ready";

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Wand2 className="w-6 h-6" /> AI Auto Clipper
        </h1>
        <p className="text-sm opacity-70">Pick a video, analyze it, then export the best non-overlapping clips.</p>
      </div>

      {error && <div className="rounded border border-red-500/50 bg-red-500/10 p-3 text-sm">{error}</div>}

      <div className="rounded-lg border border-white/10 p-4 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <select
            className="rounded border border-white/10 bg-transparent px-3 py-2"
            value={videoId ?? ""}
            onChange={(e) => setVideoId(Number(e.target.value))}
          >
            {videos.length === 0 && <option value="">No videos uploaded</option>}
            {videos.map((v) => (
              <option key={v.id} value={v.id} className="text-black">
                {v.name}
              </option>
            ))}
          </select>
          <button
            onClick={analyze}
            disabled={!!busy || videoId == null}
            className="rounded bg-violet-600 px-4 py-2 text-white disabled:opacity-50 flex items-center gap-2"
          >
            <Sparkles className="w-4 h-4" /> {ready ? "Re-analyze" : "Analyze with AI"}
          </button>
        </div>

        <div className="text-sm opacity-80">
          Analysis: <b>{analysisStatus}</b>
          {ready && ` | ${highlightCount} highlights | scoring: ${source}`}
          {note && <div className="opacity-70">{note}</div>}
        </div>

        {ready && (
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm">
              Clips:{" "}
              <input
                type="number"
                min={1}
                max={20}
                value={count}
                onChange={(e) => setCount(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
                className="w-16 rounded border border-white/10 bg-transparent px-2 py-1"
              />
            </label>
            <select
              className="rounded border border-white/10 bg-transparent px-2 py-1 text-sm"
              value={mode}
              onChange={(e) => setMode(e.target.value as "accurate" | "fast")}
            >
              <option value="accurate" className="text-black">Accurate (frame exact)</option>
              <option value="fast" className="text-black">Fast (copy, instant)</option>
            </select>
            <button
              onClick={generate}
              disabled={!!busy}
              className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"
            >
              Generate clips
            </button>
          </div>
        )}

        {busy && (
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> {busy}
          </div>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {clips.map((c) => (
          <div key={c.id} className="rounded-lg border border-white/10 overflow-hidden">
            <div className="aspect-video bg-black/40 flex items-center justify-center">
              {c.status === "ready" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={`${API}/api/clips/${c.id}/thumbnail`} alt={c.title} className="w-full h-full object-cover" />
              ) : c.status === "failed" || c.status === "cancelled" ? (
                <span className="text-sm text-red-400">{c.status}</span>
              ) : (
                <Loader2 className="w-6 h-6 animate-spin opacity-70" />
              )}
            </div>
            <div className="p-3 space-y-1">
              <div className="font-medium truncate">{c.title}</div>
              <div className="text-xs opacity-70">
                {fmt(c.start_sec)} - {fmt(c.end_sec)}
                {c.ai_score != null && ` | score ${Math.round(c.ai_score)}`} | {c.status}
              </div>
              {c.status === "ready" && (
                <div className="flex gap-3 pt-1 text-sm">
                  <a className="flex items-center gap-1 underline" href={`${API}/api/clips/${c.id}/stream`} target="_blank" rel="noreferrer">
                    <Play className="w-3 h-3" /> Play
                  </a>
                  <a className="flex items-center gap-1 underline" href={`${API}/api/clips/${c.id}/download`}>
                    <Download className="w-3 h-3" /> Download
                  </a>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}