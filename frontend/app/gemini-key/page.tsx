"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Loader2, Trash2, XCircle } from "lucide-react";
import { api } from "@/lib/api8";

type St = { configured: boolean; source: string; masked: string; model: string };

export default function GeminiKeyPage() {
  const [st, setSt] = useState<St | null>(null);
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [msg, setMsg] = useState("");
  const [ok, setOk] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setSt((await api("/api/gemini-key/status")) as St); }
    catch { setMsg("Backend not reachable. Start it with .\\scripts\\start-all.ps1"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setMsg(""); setOk(null);
    try { await fn(); } catch (e) { setMsg((e as Error).message); setOk(false); }
    setBusy(false);
  }

  const save = () => run(async () => {
    const d = (await api("/api/gemini-key", { method: "POST", body: JSON.stringify({ key }) })) as St;
    setSt(d); setKey(""); setMsg("Key saved and active now. Press Test key to check it."); setOk(true);
  });
  const test = () => run(async () => {
    const d = (await api("/api/gemini-key/test", { method: "POST" })) as { ok: boolean; error: string | null };
    setOk(d.ok); setMsg(d.ok ? "Gemini answered. The key works." : "Test failed: " + d.error);
  });
  const remove = () => run(async () => {
    const d = (await api("/api/gemini-key", { method: "DELETE" })) as St;
    setSt(d); setMsg("Saved key removed. The key from .env (if any) is used now."); setOk(true);
  });

  const src: Record<string, string> = { saved: "Saved from this page", env: "From the .env file", none: "No key" };

  return (
    <div className="p-6 space-y-5 max-w-2xl text-slate-200">
      <div className="flex items-center gap-3">
        <KeyRound className="w-7 h-7 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold">Gemini API Key</h1>
          <p className="text-sm text-slate-400">Change the key here. No .env editing and no restart needed.</p>
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-800/60 p-4 text-sm space-y-1">
        <div>Status: {st?.configured
          ? <span className="text-emerald-400">Key is set ({st.masked})</span>
          : <span className="text-amber-400">No key. Local scoring is used.</span>}</div>
        <div>Source: {st ? src[st.source] : "..."}</div>
        <div>Model: {st?.model ?? "..."}</div>
      </div>

      <div className="space-y-2">
        <label className="block text-sm">New Gemini API key
          <input type={show ? "text" : "password"} value={key} onChange={(e) => setKey(e.target.value)}
            autoComplete="off" placeholder="Paste your key here"
            className="mt-1 w-full rounded bg-slate-800 border border-slate-700 p-2 text-sm" />
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Show key while typing
        </label>
        <div className="flex flex-wrap gap-3">
          <button disabled={busy || !key.trim()} onClick={save}
            className="rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-4 py-2 text-sm font-medium">Save key</button>
          <button disabled={busy || !st?.configured} onClick={test}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-50 px-4 py-2 text-sm">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />} Test key</button>
          <button disabled={busy || st?.source !== "saved"} onClick={remove}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-600 hover:border-red-500 disabled:opacity-40 px-4 py-2 text-sm">
            <Trash2 className="w-4 h-4" /> Remove saved key</button>
        </div>
      </div>

      {msg && (
        <div className="flex items-start gap-2 rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm">
          {ok === true && <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5" />}
          {ok === false && <XCircle className="w-4 h-4 text-red-400 mt-0.5" />}
          <span>{msg}</span>
        </div>
      )}
      <p className="text-xs text-slate-500">The key is stored only on this PC (storage/settings, not uploaded anywhere) and is never shown in full. Gemini is only called when you run an AI feature.</p>
    </div>
  );
}
