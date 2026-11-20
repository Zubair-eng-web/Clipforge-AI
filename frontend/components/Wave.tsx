export default function Wave({ peaks, from = 0, to = 1, color = "#a78bfa" }: { peaks: number[]; from?: number; to?: number; color?: string }) {
  const n = peaks.length;
  const a = Math.max(0, Math.floor(from * n));
  const b = Math.min(n, Math.max(a + 1, Math.ceil(to * n)));
  const sl = peaks.slice(a, b);
  return (
    <svg viewBox={`0 0 ${sl.length || 1} 100`} preserveAspectRatio="none" className="h-full w-full">
      {sl.map((p, i) => (
        <rect key={i} x={i} y={50 - p * 48} width={0.8} height={Math.max(p * 96, 1)} fill={color} />
      ))}
    </svg>
  );
}