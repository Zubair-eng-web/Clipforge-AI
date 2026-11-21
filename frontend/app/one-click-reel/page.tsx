"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Sparkles, X } from "lucide-react";
import { API, api, rows } from "@/lib/api8";

type Clip = { id: number; title: string; status: string; duration_sec: number | null; width: number | null; height: number | null };
type Track = { id: number; name: string; folder: string };
type Plat = Record<string, { label: string; ratio: string; max_sec: number }>;
type StepState = "idle" | "running" | "done" | "skipped" | "failed";
type Step = { key: string; label: string; state: StepState; note: string };
type IdReply = { clip_id?: number; clip?: { id?: number }; job_id?: number };

const PRESETS: [string, string][] = [
  ["gaming", "Gaming"], ["viral_reels", "Viral Reels"], ["cinematic", "Cinematic"], ["bold_highlight", "Bold Highlight"],
  ["minimal", "Minimal"], ["word_by_word", "Word by Word"], ["karaoke", "Karaoke"],
];
const TONES = ["viral", "funny", "cinematic", "professional", "suspenseful", "minimal"];
const LANGS: [string, string][] = [["", "Auto detect"], ["en", "English"], ["ur", "Urdu"], ["hi", "Hindi"], ["ar", "Arabic"]];
const LENGTHS = [0, 15, 30, 45, 60, 90];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function OneClickReelPage() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [clipId, setClipId] = useState<number | null>(null);
  const [plats, setPlats] = useState<Plat>({});
  const [platform, setPlatform] = useState("youtube_shorts");
  const [size, setSize] = useState("720");
  const [mode, setMode] = useState("face");
  const [length, setLength] = useState(30);
  const [trimDead, setTrimDead] = useState(true);
  const [introOn, setIntroOn] = useState(false);
  const [introText, setIntroText] = useState("");
  const [outroOn, setOutroOn] = useState(false);
  const [outroText, setOutroText] = useState("");
  const [capsOn, setCapsOn] = useState(true);
  const [preset, setPreset] = useState("gaming");
  const [lang, setLang] = useState("");
  const [musicOn, setMusicOn] = useState(false);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [trackId, setTrackId] = useState<number | null>(null);
  const [musicVol, setMusicVol] = useState(40);
  const [keepOrig, setKeepOrig] = useState(true);
  const [origVol, setOrigVol] = useState(100);
  const [socialOn, setSocialOn] = useState(true);
  const [tone, setTone] = useState("viral");
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [msg, setMsg] = useState("");
  const [finalId, setFinalId] = useState<number | null>(null);
  const [social, setSocial] = useState<Record<string, unknown> | null>(null);
  const cancel = useRef(false);
  const jobRef = useRef<number | null>(null);

  useEffect(() => {
    api("/api/clips?limit=200")
      .then((d) => {
        const list = (rows(d) as Clip[]).filter((c) => c.status === "ready");
        setClips(list);
        if (list.length) setClipId(list[0].id);
      })
      .catch(() => setMsg("Backend not reachable. Start it with .\\scripts\\start-all.ps1"));
    api("/api/reels-studio/platforms").then((d) => setPlats((d.platforms ?? {}) as Plat)).catch(() => {});
    api("/api/music")
      .then((d) => {
        const t = rows(d) as Track[];
        setTracks(t);
        if (t.length) setTrackId(t[0].id);
      })
      .catch(() => {});
  }, []);

  const platKeys = Object.keys(plats).length ? Object.keys(plats) : ["youtube_shorts"];
  const maxSec = plats[platform]?.max_sec ?? 180;
  const mark = (key: string, state: StepState, note = "") =>
    setSteps((p) => p.map((s) => (s.key === key ? { ...s, state, note } : s)));

  async function maxId(): Promise<number> {
    const list = rows(await api("/api/clips?limit=5")) as Clip[];
    return list.reduce((m, c) => Math.max(m, c.id), 0);
  }

  async function waitJob(jobId: number) {
    jobRef.current = jobId;
    for (let i = 0; i < 1800; i++) {
      if (cancel.current) throw new Error("Cancelled");
      const j = await api(`/api/jobs/${jobId}`);
      const st = String(j.status || "");
      if (st === "completed") return;
      if (st === "failed" || st === "cancelled") throw new Error(`Job ${st}: ${j.error || ""}`);
      await sleep(2000);
    }
    throw new Error("Job timeout");
  }

  async function waitClip(id: number): Promise<Clip> {
    for (let i = 0; i < 900; i++) {
      if (cancel.current) throw new Error("Cancelled");
      const c = (await api(`/api/clips/${id}`)) as Clip;
      if (c.status === "ready") return c;
      if (c.status === "failed" || c.status === "cancelled") throw new Error(`Clip ${id} ${c.status}`);
      await sleep(2000);
    }
    throw new Error("Clip timeout");
  }

  async function resultClip(d: IdReply, before: number): Promise<number> {
    const id = d.clip_id ?? d.clip?.id;
    if (id) return id;
    if (d.job_id) await waitJob(d.job_id);
    const list = rows(await api("/api/clips?limit=10")) as Clip[];
    const top = list.filter((c) => c.id > before).sort((a, b) => b.id - a.id)[0];
    if (!top) throw new Error("The new clip was not found");
    return top.id;
  }

  async function run() {
    if (clipId === null) return;
    const src = clips.find((c) => c.id === clipId);
    const base = (src?.title || `clip ${clipId}`).slice(0, 120);
    const list: Step[] = [{ key: "reel", label: "1. Make the reel", state: "idle", note: "" }];
    if (capsOn) list.push({ key: "captions", label: "2. Captions", state: "idle", note: "" });
    if (musicOn) list.push({ key: "music", label: "3. Music", state: "idle", note: "" });
    if (socialOn) list.push({ key: "social", label: "4. Title, description, hashtags", state: "idle", note: "" });
    if (musicOn && trackId === null) { setMsg("Choose a music track first (Music Library)."); return; }
    cancel.current = false; jobRef.current = null;
    setSteps(list); setFinalId(null); setSocial(null); setMsg(""); setRunning(true);
    let cur = clipId;
    let active = "reel";
    try {
      // 1) reel
      mark("reel", "running");
      let before = await maxId();
      const body: Record<string, unknown> = {
        clip_id: cur, platform, ratio: plats[platform]?.ratio ?? "9:16", size, mode, trim_dead_time: trimDead,
        original_audio_on: true, original_volume: 1, title: `${base} (reel)`,
      };
      if (length > 0) body.target_sec = length;
      if (introOn && introText.trim()) body.intro = { text: introText.trim().slice(0, 80), seconds: 2, bg: "#000000", fg: "#FFFFFF" };
      if (outroOn && outroText.trim()) body.outro = { text: outroText.trim().slice(0, 80), seconds: 2, bg: "#000000", fg: "#FFFFFF" };
      const r = await api("/api/reels-studio/create", { method: "POST", body: JSON.stringify(body) });
      if (r.job_id) jobRef.current = r.job_id;
      cur = await resultClip(r, before);
      await waitClip(cur);
      mark("reel", "done", `clip #${cur}`);

      // 2) captions (a failure here never stops the rest)
      if (capsOn) {
        active = "captions";
        mark("captions", "running", "Whisper is listening...");
        try {
          const g = await api(`/api/clips/${cur}/captions/generate`, { method: "POST", body: JSON.stringify(lang ? { language: lang } : {}) });
          if (g && g.job_id) await waitJob(g.job_id);
          const cap = await api(`/api/clips/${cur}/captions`);
          const lines = (cap.segments ?? cap.lines ?? []) as unknown[];
          if (!lines.length) {
            mark("captions", "skipped", "No speech found, so no captions were added (nothing is invented).");
          } else {
            mark("captions", "running", `${lines.length} lines, burning into the video...`);
            before = await maxId();
            const b = await api(`/api/clips/${cur}/captions/studio-burn`, { method: "POST", body: JSON.stringify({ preset }) });
            const nid = await resultClip(b, before);
            await waitClip(nid);
            cur = nid;
            mark("captions", "done", `${lines.length} lines, clip #${cur}`);
          }
        } catch (e) {
          if (cancel.current) throw e;
          mark("captions", "failed", (e as Error).message + " (continuing without captions)");
        }
      }

      // 3) music
      if (musicOn) {
        active = "music";
        mark("music", "running");
        const m = await api(`/api/audio-studio/clips/${cur}/mix`, {
          method: "POST",
          body: JSON.stringify({
            original_enabled: keepOrig, original_volume: origVol, codec: "aac", bitrate_kbps: 192, title: `${base} (music)`,
            tracks: [{ track_id: trackId, volume: musicVol, loop: true, fade_in: 1, fade_out: 2, start_sec: 0, trim_in: 0 }],
          }),
        });
        if (m.job_id) jobRef.current = m.job_id;
        const nid = (m.clip_id ?? m.clip?.id) as number;
        await waitClip(nid);
        cur = nid;
        mark("music", "done", `clip #${cur}`);
      }

      // 4) social text
      if (socialOn) {
        active = "social";
        mark("social", "running");
        try {
          const s = await api("/api/social/generate", { method: "POST", body: JSON.stringify({ clip_id: cur, tone, platform: "general", notes: "" }) });
          setSocial(s as Record<string, unknown>);
          mark("social", "done", String(s.source ?? ""));
        } catch (e) {
          mark("social", "failed", (e as Error).message);
        }
      }
      setFinalId(cur);
      setMsg("Done. Your reel is ready below. It is also in Generated Clips.");
    } catch (e) {
      mark(active, "failed", (e as Error).message);
      setMsg((e as Error).message === "Cancelled" ? "Cancelled." : "Stopped: " + (e as Error).message);
    }
    setRunning(false);
  }

  async function stop() {
    cancel.current = true;
    if (jobRef.current) { try { await api(`/api/jobs/${jobRef.current}/cancel`, { method: "POST" }); } catch { /* already finished */ } }
  }

  const copy = (t: string) => { navigator.clipboard?.writeText(t).catch(() => setMsg("Copy failed, select the text by hand.")); };
  const field = (k: string) => { const v = social?.[k]; return Array.isArray(v) ? v.join(" ") : String(v ?? ""); };
  const sel = "w-full rounded-lg bg-slate-800 border border-slate-700 p-2 text-sm";
  const box = "rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-2";

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <div className="flex items-center gap-3">
        <Sparkles className="w-7 h-7 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold">One-Click Reel</h1>
          <p className="text-sm text-slate-400">Reel + captions + your own music + title and hashtags, in one go. Every result is a NEW clip, the original stays untouched.</p>
        </div>
      </div>
      {msg && <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">{msg}</div>}

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className={box}>
            <h2 className="font-semibold">1. Source clip and reel</h2>
            <select className={sel} value={clipId ?? ""} onChange={(e) => setClipId(Number(e.target.value))}>
              {clips.length === 0 && <option value="">No ready clips yet (make one in Gaming Highlights or Manual Clipper)</option>}
              {clips.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.title} ({Math.round(c.duration_sec ?? 0)}s, {c.width}x{c.height})</option>)}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <select className={sel} value={platform} onChange={(e) => setPlatform(e.target.value)}>
                {platKeys.map((k) => <option key={k} value={k}>{plats[k]?.label ?? k}</option>)}
              </select>
              <select className={sel} value={size} onChange={(e) => setSize(e.target.value)}>
                <option value="720">720 x 1280 (light)</option>
                <option value="1080">1080 x 1920 (heavy)</option>
              </select>
              <select className={sel} value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="face">Face (fixed crop)</option><option value="center">Center</option><option value="blur">Blurred background</option>
              </select>
              <select className={sel} value={length} onChange={(e) => setLength(Number(e.target.value))}>
                {LENGTHS.filter((n) => n === 0 || n <= maxSec).map((n) => <option key={n} value={n}>{n === 0 ? "Full clip" : `${n} seconds`}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={trimDead} onChange={(e) => setTrimDead(e.target.checked)} /> Trim dead time (quiet start/end)</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={introOn} onChange={(e) => setIntroOn(e.target.checked)} /> Intro text card</label>
            {introOn && <input className={sel} maxLength={80} placeholder="Intro text" value={introText} onChange={(e) => setIntroText(e.target.value)} />}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={outroOn} onChange={(e) => setOutroOn(e.target.checked)} /> Outro text card</label>
            {outroOn && <input className={sel} maxLength={80} placeholder="Outro text" value={outroText} onChange={(e) => setOutroText(e.target.value)} />}
          </div>

          <div className={box}>
            <label className="flex items-center gap-2 font-semibold"><input type="checkbox" checked={capsOn} onChange={(e) => setCapsOn(e.target.checked)} /> 2. Captions (from real speech)</label>
            {capsOn && (
              <div className="grid grid-cols-2 gap-2">
                <select className={sel} value={preset} onChange={(e) => setPreset(e.target.value)}>{PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
                <select className={sel} value={lang} onChange={(e) => setLang(e.target.value)}>{LANGS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
                <p className="col-span-2 text-xs text-slate-400">No speech = no captions (nothing is invented). Whisper needs some RAM, close other apps on an 8 GB PC.</p>
              </div>
            )}
          </div>

          <div className={box}>
            <label className="flex items-center gap-2 font-semibold"><input type="checkbox" checked={musicOn} onChange={(e) => setMusicOn(e.target.checked)} /> 3. Music (from your own library)</label>
            {musicOn && (tracks.length === 0
              ? <p className="text-sm text-amber-400">Your Music Library is empty. Upload your own tracks in Music Library first.</p>
              : (
                <div className="space-y-2">
                  <select className={sel} value={trackId ?? ""} onChange={(e) => setTrackId(Number(e.target.value))}>
                    {tracks.map((t) => <option key={t.id} value={t.id}>{t.name}{t.folder ? ` (${t.folder})` : ""}</option>)}
                  </select>
                  <label className="flex items-center gap-2 text-sm">Music volume {musicVol}%
                    <input type="range" min={0} max={100} value={musicVol} onChange={(e) => setMusicVol(Number(e.target.value))} /></label>
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={keepOrig} onChange={(e) => setKeepOrig(e.target.checked)} /> Keep original sound</label>
                  {keepOrig && <label className="flex items-center gap-2 text-sm">Original volume {origVol}%
                    <input type="range" min={0} max={100} value={origVol} onChange={(e) => setOrigVol(Number(e.target.value))} /></label>}
                </div>
              ))}
          </div>

          <div className={box}>
            <label className="flex items-center gap-2 font-semibold"><input type="checkbox" checked={socialOn} onChange={(e) => setSocialOn(e.target.checked)} /> 4. Title, description, hashtags</label>
            {socialOn && (
              <>
                <select className={sel} value={tone} onChange={(e) => setTone(e.target.value)}>{TONES.map((t) => <option key={t} value={t}>{t}</option>)}</select>
                <p className="text-xs text-slate-400">With a Gemini key, the clip title, description and speech TEXT (no video frames) go to Google Gemini. Without a key a local template is used.</p>
              </>
            )}
          </div>

          <div className="flex gap-3">
            <button disabled={running || clipId === null} onClick={run}
              className="inline-flex items-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-5 py-2.5 font-medium">
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {running ? "Working..." : "Create Reel"}
            </button>
            {running && <button onClick={stop} className="rounded-lg bg-slate-700 hover:bg-slate-600 px-4 py-2 text-sm">Cancel</button>}
          </div>
        </div>

        <div className="space-y-4">
          {steps.length > 0 && (
            <div className={box}>
              <h2 className="font-semibold">Progress</h2>
              {steps.map((s) => (
                <div key={s.key} className="flex items-start gap-2 text-sm">
                  <span className="w-5 pt-0.5">
                    {s.state === "running" ? <Loader2 className="w-4 h-4 animate-spin" /> : s.state === "done" ? <Check className="w-4 h-4 text-emerald-400" />
                      : s.state === "failed" ? <X className="w-4 h-4 text-red-400" /> : s.state === "skipped" ? "-" : "."}
                  </span>
                  <div><div>{s.label}</div>{s.note && <div className="text-xs text-slate-400">{s.note}</div>}</div>
                </div>
              ))}
            </div>
          )}
          {finalId !== null && (
            <div className={box}>
              <h2 className="font-semibold">Result (clip #{finalId})</h2>
              <video controls className="w-full max-h-[480px] rounded-lg bg-black" src={`${API}/api/clips/${finalId}/stream`} />
              <div className="flex flex-wrap gap-3 text-sm">
                <a className="underline" href={`${API}/api/clips/${finalId}/download`}>Download MP4</a>
                <a className="underline" href="/clips-gallery">Open Clips Gallery</a>
              </div>
            </div>
          )}
          {social && (
            <div className={box}>
              <h2 className="font-semibold">Text for your post (check and edit before using)</h2>
              {["title", "description", "caption", "hashtags", "cta", "pinned_comment"].map((k) => (
                <div key={k}>
                  <div className="flex items-center justify-between text-xs text-slate-400"><span>{k.replace("_", " ")}</span>
                    <button className="underline" onClick={() => copy(field(k))}>Copy</button></div>
                  <div className="rounded bg-slate-800 border border-slate-700 p-2 text-sm whitespace-pre-wrap">{field(k) || "-"}</div>
                </div>
              ))}
              {field("warning") && <p className="text-xs text-amber-400">{field("warning")}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}