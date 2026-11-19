"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { UploadCloud, CheckCircle2, AlertTriangle, Loader2, Clock } from "lucide-react";
import { API, ALLOWED_EXT, fmtBytes, fmtDuration, type VideoItem } from "@/lib/api";

type Item = {
  key: string;
  file: File;
  status: "queued" | "uploading" | "done" | "error";
  progress: number;
  error?: string;
  video?: VideoItem;
};

export default function UploadPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const chain = useRef<Promise<void>>(Promise.resolve());
  const inputRef = useRef<HTMLInputElement>(null);

  const patch = (key: string, p: Partial<Item>) =>
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, ...p } : i)));

  function uploadOne(item: Item): Promise<void> {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API}/api/videos/upload`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) patch(item.key, { progress: Math.round((e.loaded / e.total) * 100) });
      };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300 && data.uploaded?.length) {
            patch(item.key, { status: "done", progress: 100, video: data.uploaded[0] });
          } else {
            patch(item.key, {
              status: "error",
              error: data.errors?.[0]?.error ?? data.detail ?? `Upload failed (${xhr.status})`,
            });
          }
        } catch {
          patch(item.key, { status: "error", error: `Upload failed (${xhr.status})` });
        }
        resolve();
      };
      xhr.onerror = () => {
        patch(item.key, { status: "error", error: "Cannot reach the backend. Is it running?" });
        resolve();
      };
      const form = new FormData();
      form.append("files", item.file);
      patch(item.key, { status: "uploading", progress: 0 });
      xhr.send(form);
    });
  }

  function addFiles(list: FileList | File[]) {
    const fresh: Item[] = Array.from(list).map((file, idx) => {
      const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
      const ok = ALLOWED_EXT.includes(ext);
      return {
        key: `${Date.now()}-${idx}-${file.name}`,
        file,
        status: ok ? "queued" : "error",
        progress: 0,
        error: ok ? undefined : `Unsupported file type "${ext}"`,
      } as Item;
    });
    setItems((prev) => [...fresh, ...prev]);
    for (const it of fresh) {
      if (it.status === "queued") chain.current = chain.current.then(() => uploadOne(it));
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-white">Upload Videos</h1>
      <p className="text-sm text-zinc-400">
        MP4, MOV, MKV, AVI, WebM, MP3, WAV. Files are saved permanently on this computer.
      </p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        className={`mt-6 cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          dragging ? "border-violet-500 bg-violet-600/10" : "border-zinc-700 bg-zinc-900/40 hover:border-zinc-500"
        }`}
      >
        <UploadCloud className="mx-auto text-violet-400" size={42} />
        <p className="mt-3 font-medium text-white">Drag and drop videos here</p>
        <p className="text-sm text-zinc-400">or click to browse files (multiple allowed)</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ALLOWED_EXT.join(",")}
          className="hidden"
          onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
        />
      </div>

      <div className="mt-6 space-y-3">
        {items.map((it) => (
          <div key={it.key} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium text-white">{it.file.name}</p>
                <p className="text-xs text-zinc-500">{fmtBytes(it.file.size)}</p>
              </div>
              <div className="shrink-0 text-sm">
                {it.status === "queued" && <span className="flex items-center gap-1 text-zinc-400"><Clock size={16} /> Waiting</span>}
                {it.status === "uploading" && (
                  <span className="flex items-center gap-1 text-violet-300">
                    <Loader2 size={16} className="animate-spin" />
                    {it.progress >= 100 ? "Validating with FFprobe..." : `${it.progress}%`}
                  </span>
                )}
                {it.status === "done" && <span className="flex items-center gap-1 text-emerald-400"><CheckCircle2 size={16} /> Saved</span>}
                {it.status === "error" && <span className="flex items-center gap-1 text-red-400"><AlertTriangle size={16} /> Failed</span>}
              </div>
            </div>

            {it.status === "uploading" && (
              <div className="mt-3 h-1.5 overflow-hidden rounded bg-zinc-800">
                <div className="h-full bg-violet-500 transition-all" style={{ width: `${it.progress}%` }} />
              </div>
            )}
            {it.status === "done" && it.video && (
              <p className="mt-2 text-xs text-zinc-400">
                Duration {fmtDuration(it.video.duration_sec)}
                {it.video.width ? ` | ${it.video.width}x${it.video.height}` : " | audio only"}
              </p>
            )}
            {it.status === "error" && <p className="mt-2 text-xs text-red-400">{it.error}</p>}
          </div>
        ))}
      </div>

      {items.some((i) => i.status === "done") && (
        <Link href="/library" className="mt-6 inline-block rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500">
          Open Video Library
        </Link>
      )}
    </div>
  );
}