"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Play, ScanLine, Scissors } from "lucide-react";
import { API, fmtClock, watchJob, type VideoItem } from "@/lib/api";

type SceneRow = { idx: number; start_sec: number; end_sec: number };

export default function SceneDetectionPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [scenes, setScenes] = useState<SceneRow[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [minLen, setMinLen] = useState(2);
  const [sent, setSent] = useState<number[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);
  const stopRef = useRef<(() => void) | null>(null);

  const loadScenes = useCallback(async (id: number) => {
    try {
      const r = await fetch(`${API}/api/analysis/videos/${id}/scenes`);
      if (!r.ok) throw new Error();
      const d = (await r.json()) as { items: SceneRow[] };
      setScenes(d.items);
    } catch {
      setScenes([]);
    }
  }, []);

  useEffect(() => {
    fetch(`${API}/api/videos?limit=500`)
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then((d: { items: VideoItem[] }) => {
        const list = d.items.filter((v) => v.has_video);
        setVideos(list);
        if (list.length) setVideoId(list[0].id);
      })
      .catch(() => setMsg("Cannot reach the backend. Start it with .\\scripts\\start-all.ps1"));
    return () => stopRef.current?.();
  }, []);

  useEffect(() => {
    stopRef.current?.();
    stopRef.current = null;
    setProgress(null);
    setMsg("");
    setSent([]);
    setScenes([]);
    if (videoId !== null) loadScenes(videoId);
  }, [videoId, loadScenes]);

  async function detect() {
    if (videoId === null) return;
    const id = videoId;
    setMsg("");
    const r = await fetch(`${API}/api/analysis/videos/${id}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps: ["scenes"] }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setMsg(typeof data.detail === "string" ? data.detail : "Could not start scene detection.");
      return;
    }
    setProgress(0);
    stopRef.current = watchJob(data.job_id, (j) => {
      setProgress(j.progress);
      if (["completed", "failed", "cancelled"].includes(j.status)) {
        setProgress(null);
        if (j.status !== "completed") setMsg(j.error || `Job ${j.status}`);
        loadScenes(id);
      }
    });
  }

  async function exportScene(s: SceneRow) {
    if (videoId === null) return;
    const r = await fetch(`${API}/api/clips`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_id: videoId,
        start_sec: s.start_sec,
        end_sec: s.end_sec,
        title: `Scene ${s.idx + 1}`,
        mode: "accurate",
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok) {
      setSent((p) => [...p, s.idx]);
      setMsg(`Scene ${s.idx + 1} queued for export. Check Generated Clips.`);
    } else {
      setMsg(typeof data.detail === "string" ? data.detail : "Could not create the clip.");
    }
  }

  function playFrom(s: SceneRow) {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = s.start_sec;
    v.play().catch(() => setMsg("This format cannot play in the browser. Use the Manual Clipper preview."));
  }

  const busy = progress !== null;
  const total = scenes.length ? scenes[scenes.length - 1].end_sec : 0;
  const shown = scenes.filter((s) => s.end_sec - s.start_sec >= minLen);

  return (
    <div className="max-w-5xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
        <ScanLine className="text-violet-400" size={24} /> Scene Detection
      </h1>
      <p className="text-sm text-zinc-400">Finds the cuts in a video so you can jump to or clip any scene.</p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <select
          value={videoId ?? ""}
          onChange={(e) => setVideoId(e.target.value ? Number(e.target.value) : null)}
          className="min-w-64 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
        >
          {videos.length === 0 && <option value="">No videos uploaded</option>}
          {videos.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
        <button
          onClick={detect}
          disabled={videoId === null || busy}
          className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <ScanLine size={16} />}
          {scenes.length ? "Detect again" : "Detect scenes"}
        </button>
        {scenes.length > 0 && (
          <label className="text-sm text-zinc-400">
            Hide scenes shorter than{" "}
            <input
              type="number"
              min={0}
              step={0.5}
              value={minLen}
              onChange={(e) => setMinLen(Math.max(0, Number(e.target.value) || 0))}
              className="w-16 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-white"
            />{" "}
            s
          </label>
        )}
      </div>

      {busy && (
        <div className="mt-4">
          <div className="h-2 w-full overflow-hidden rounded bg-zinc-800">
            <div className="h-2 bg-violet-500 transition-all" style={{ width: `${Math.min(progress ?? 0, 100)}%` }} />
          </div>
          <p className="mt-1 text-xs text-zinc-400">Detecting scenes... {Math.round(progress ?? 0)}%</p>
        </div>
      )}

      {msg && <p className="mt-4 rounded-lg bg-zinc-900 p-3 text-sm text-amber-300">{msg}</p>}

      {videoId !== null && (
        <video
          key={videoId}
          ref={videoRef}
          controls
          className="mt-6 max-h-80 w-full rounded-xl bg-black"
          src={`${API}/api/videos/${videoId}/stream`}
        />
      )}

      {scenes.length > 0 && (
        <>
          <div className="mt-4 flex h-6 w-full overflow-hidden rounded bg-zinc-800">
            {scenes.map((s) => (
              <div
                key={s.idx}
                title={`Scene ${s.idx + 1}: ${fmtClock(s.start_sec)} - ${fmtClock(s.end_sec)}`}
                className={s.idx % 2 === 0 ? "bg-violet-600/70" : "bg-violet-400/70"}
                style={{ width: `${((s.end_sec - s.start_sec) / (total || 1)) * 100}%` }}
              />
            ))}
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            {scenes.length} scenes found, {shown.length} shown
          </p>

          <div className="mt-3 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="px-4 py-3">Scene</th>
                  <th className="px-4 py-3">Start</th>
                  <th className="px-4 py-3">End</th>
                  <th className="px-4 py-3">Length</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((s) => (
                  <tr key={s.idx} className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/40">
                    <td className="px-4 py-2 text-white">#{s.idx + 1}</td>
                    <td className="px-4 py-2 text-zinc-300">{fmtClock(s.start_sec)}</td>
                    <td className="px-4 py-2 text-zinc-300">{fmtClock(s.end_sec)}</td>
                    <td className="px-4 py-2 text-zinc-300">{(s.end_sec - s.start_sec).toFixed(1)}s</td>
                    <td className="px-4 py-2">
                      <div className="flex justify-end gap-2">
                        <button onClick={() => playFrom(s)} className="rounded-md bg-zinc-800 p-2 hover:bg-zinc-700" title="Play from here">
                          <Play size={15} />
                        </button>
                        <button
                          onClick={() => exportScene(s)}
                          disabled={sent.includes(s.idx)}
                          className="rounded-md bg-zinc-800 p-2 text-violet-300 hover:bg-zinc-700 disabled:opacity-40"
                          title="Export this scene as a clip"
                        >
                          <Scissors size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}