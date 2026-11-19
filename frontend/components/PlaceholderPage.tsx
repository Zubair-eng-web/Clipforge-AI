export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-white">{title}</h1>
      <div className="mt-6 rounded-xl border border-dashed border-zinc-700 bg-zinc-900/40 p-10 text-center text-zinc-400">
        This module is coming in an upcoming phase.
      </div>
    </div>
  );
}