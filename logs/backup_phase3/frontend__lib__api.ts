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