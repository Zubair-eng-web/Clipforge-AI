export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const ALLOWED_EXT = [".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav"];

export type VideoItem = {
  id: number;
  name: string;
  size_bytes: number;
  duration_sec: number | null;
  width: number | null;
  height: number | null;
  format: string | null;
  status: string;
  has_video: boolean;
  created_at: string;
};

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
  return `${n.toFixed(1)} ${units[i]}`;
}

export function fmtDuration(sec: number | null): string {
  if (sec == null) return "-";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(r)}` : `${m}:${pad(r)}`;
}

export type ClipItem = {
  id: number;
  video_id: number;
  title: string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  width: number | null;
  height: number | null;
  aspect_ratio: string | null;
  status: string;
  ai_score: number | null;
  has_file: boolean;
  has_thumbnail: boolean;
  created_at: string;
};

export type JobItem = {
  id: number;
  type: string;
  video_id: number | null;
  status: string;
  progress: number; // percent 0..100
  error: string | null;
  created_at: string;
  updated_at: string;
};

export function fmtClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

/** Live job progress via Server-Sent Events. Returns a function that stops listening. */
export function watchJob(jobId: number, onUpdate: (j: JobItem) => void): () => void {
  const es = new EventSource(`${API}/api/jobs/${jobId}/events`);
  es.onmessage = (e) => {
    try {
      const j = JSON.parse(e.data) as JobItem;
      onUpdate(j);
      if (["completed", "failed", "cancelled"].includes(j.status)) es.close();
    } catch {
      /* ignore malformed event */
    }
  };
  es.onerror = () => {
    es.close();
    onUpdate({
      id: jobId, type: "", video_id: null, status: "failed", progress: 0,
      error: "Lost connection to the backend", created_at: "", updated_at: "",
    });
  };
  return () => es.close();
}
