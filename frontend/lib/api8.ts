/* eslint-disable @typescript-eslint/no-explicit-any */
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function api(path: string, init?: RequestInit): Promise<any> {
  const r = await fetch(API + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...((init && init.headers) || {}) },
  });
  if (!r.ok) {
    let m: any = r.statusText;
    try {
      const d = await r.json();
      m = d.detail || m;
    } catch {}
    throw new Error(typeof m === "string" ? m : JSON.stringify(m));
  }
  return r.json();
}

export const rows = (d: any): any[] => (Array.isArray(d) ? d : d?.items ?? d?.videos ?? d?.clips ?? []);

export function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + u[i];
}

export function fmtDur(s: number | null | undefined): string {
  if (s == null) return "-";
  const m = Math.floor(s / 60);
  return m + ":" + String(Math.round(s % 60)).padStart(2, "0");
}