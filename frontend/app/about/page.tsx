"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type About = {
  name: string; tagline: string; version: string; mode: string; python: string;
  features: string[]; rules: string[]; notice: string;
};

export default function AboutPage() {
  const [a, setA] = useState<About | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    fetch(`${API}/api/about`)
      .then((r) => r.json())
      .then(setA)
      .catch((e) => setErr(String(e)));
  }, []);
  return (
    <div className="max-w-3xl space-y-4 p-6 text-zinc-200">
      <h1 className="text-2xl font-semibold text-zinc-50">About CLIPFORGE AI</h1>
      {err && <p className="text-red-400">Backend se data nahi mila ({err}).</p>}
      {a && (
        <>
          <p className="text-lg">{a.tagline}</p>
          <p className="text-sm text-zinc-400">Version {a.version} | Python {a.python} | {a.mode}</p>
          <h2 className="pt-2 font-medium text-zinc-100">Features</h2>
          <ul className="list-disc pl-5 text-sm">{a.features.map((f) => <li key={f}>{f}</li>)}</ul>
          <h2 className="pt-2 font-medium text-zinc-100">Rules</h2>
          <ul className="list-disc pl-5 text-sm">{a.rules.map((f) => <li key={f}>{f}</li>)}</ul>
          <p className="rounded-lg border border-amber-700/50 bg-amber-950/30 p-3 text-sm text-amber-200">{a.notice}</p>
        </>
      )}
    </div>
  );
}