"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Scissors, Sparkles } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type VideoItem = { id: number; name: string };
type RawVideo = { id: number; original_name?: string; name?: string; title?: string };
type Segment = { start: number; end: number; text: string };
type Scene = { index: number; start: number; end: number };
type Highlight = {
  rank: number;
  start: number;
  end: number;
  duration: number;
  score: number;
  local_score: number;
  title: string;
  reason: string;
  text: string;
  source: string;
};
type Analysis = {
  status: string;
  language?: string | null;
  scoring_source?: string | null;
  note?: string | null;
  error?: string | null;
  segment_count?: number;
  scenes?: Scene[];
  highlights?: Highlight[];
  transcript?: Segment[];
};

const fmt = (sec: number) => {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const JSON_HEADERS = { "Content-Type": "application/json" };

export default function AiHighlightsPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [showTranscript, setShowTranscript] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetch(`${API}/api/videos`)
      .then((r) => r.json())
      .then((data) => {
        const list: RawVideo[] = Array.isArray(data) ? data : data.items ?? data.videos ?? [];
        setVideos(
          list.map((v) => ({
            id: v.id,
            name: v.original_name ?? v.name ?? v.title ?? `Video ${v.id}`,
          }))
        );
      })
      .catch(() => setMsg("Cannot reach the backend at " + API));
    return () => esRef.current?.close();
  }, []);

  const loadAnalysis = useCallback(async (id: number) => {
    try {
      const r = await fetch(`${API}/api/videos/${id}/analysis`);
      setAnalysis(r.ok ? await r.json() : null);
    } catch {
      setAnalysis(null);
    }
  }, []);

  function pick(id: number | null) {
    esRef.current?.close();
    setProgress(null);
    setMsg("");
    setVideoId(id);
    setAnalysis(null);
    setShowTranscript(false);
    if (id !== null) loadAnalysis(id);
  }

  async function startAnalysis() {
    if (videoId === null) return;
    const id = videoId;
    setMsg("");
    const r = await fetch(`${API}/api/videos/${id}/analyze`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ language: null, use_gemini: true }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setMsg(typeof data.detail === "string" ? data.detail : "Could not start the analysis.");
      return;
    }
    setProgress(0);
    const es = new EventSource(`${API}/api/jobs/${data.job_id}/events`);
    esRef.current = es;
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (typeof d.progress === "number") setProgress(d.progress);
      if (["completed", "failed", "cancelled"].includes(d.status)) {
        es.close();
        setProgress(null);
        if (d.status !== "completed") setMsg(d.error || `Job ${d.status}`);
        loadAnalysis(id);
      }
    };
    es.onerror = () => {
      es.close();
      setProgress(null);
      loadAnalysis(id);
    };
  }

  async function exportClip(h: Highlight) {
    if (videoId === null) return;
    const r = await fetch(`${API}/api/clips`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        video_id: videoId,
        start_sec: h.start,
        end_sec: h.end,
        title: h.title || `Highlight ${h.rank}`,
        mode: "accurate",
      }),
    });
    const data = await r.json().catch(() => ({}));
    setMsg(
      r.ok
        ? `Highlight #${h.rank} queued for export. Check Generated Clips.`
        : typeof data.detail === "string"
        ? data.detail
        : "Clip export failed."
    );
  }

  const busy = progress !== null;
  const highlights = analysis?.highlights ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6 text-zinc-100">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <Sparkles className="h-6 w-6 text-violet-400" /> AI Highlights
        </h1>
        <p className="text-sm text-zinc-400">
          Transcript, scenes and AI scores to find the best moments of a video.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={videoId ?? ""}
          onChange={(e) => pick(e.target.value ? Number(e.target.value) : null)}
          className="min-w-64 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm"
        >
          <option value="">Select a video...</option>
          {videos.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
        <button
          onClick={startAnalysis}
          disabled={videoId === null || busy}
          className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium hover:bg-violet-500 disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {analysis?.status === "ready" ? "Analyze again" : "Analyze"}
        </button>
      </div>

      {busy && (
        <div>
          <div className="h-2 w-full overflow-hidden rounded bg-zinc-800">
            <div
              className="h-2 bg-violet-500 transition-all"
              style={{ width: `${Math.min(progress ?? 0, 100)}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            Analyzing... {Math.round(progress ?? 0)}% (first run downloads the Whisper model)
          </p>
        </div>
      )}

      {msg && <p className="rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}

      {analysis?.status === "failed" && (
        <p className="rounded-lg bg-zinc-900 p-3 text-sm text-red-400">
          Last analysis failed: {analysis.error}
        </p>
      )}

      {analysis?.status === "ready" && (
        <div className="space-y-4">
          <p className="text-sm text-zinc-400">
            Language: {analysis.language ?? "?"} | {analysis.segment_count ?? 0} segments |{" "}
            {analysis.scenes?.length ?? 0} scenes | scoring: {analysis.scoring_source}
          </p>
          {analysis.note && <p className="text-sm text-amber-300">{analysis.note}</p>}
          {highlights.length === 0 && (
            <p className="text-sm text-zinc-400">No highlights found for this video.</p>
          )}
          {highlights.map((h) => (
            <div key={h.rank} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-zinc-500">
                    #{h.rank} | {fmt(h.start)} - {fmt(h.end)} ({Math.round(h.duration)}s)
                  </div>
                  <div className="font-semibold">{h.title}</div>
                  <div className="text-xs text-zinc-400">{h.reason}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-violet-400">{Math.round(h.score)}</div>
                  <div className="text-[10px] uppercase text-zinc-500">{h.source}</div>
                </div>
              </div>
              <p className="mt-2 text-sm text-zinc-300">{h.text}</p>
              <button
                onClick={() => exportClip(h)}
                className="mt-3 inline-flex items-center gap-1 rounded-lg bg-violet-600 px-3 py-1.5 text-sm hover:bg-violet-500"
              >
                <Scissors className="h-4 w-4" /> Export clip
              </button>
            </div>
          ))}

          <button
            onClick={() => setShowTranscript((s) => !s)}
            className="text-sm text-violet-400 hover:underline"
          >
            {showTranscript ? "Hide transcript" : "Show transcript"}
          </button>
          {showTranscript && (
            <div className="max-h-96 space-y-1 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm">
              {(analysis.transcript ?? []).map((s, i) => (
                <p key={i}>
                  <span className="mr-2 text-xs text-zinc-500">{fmt(s.start)}</span>
                  {s.text}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}