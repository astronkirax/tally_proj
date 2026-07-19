"use client";

import { motion } from "framer-motion";
import { compactInr } from "@/lib/utils";

/* -------------------------------------------------- Balance timeline (area) */
export function BalanceArea({ points, height = 200 }: { points: number[]; height?: number }) {
  const W = 1000;
  const H = height;
  if (points.length < 2) return <div style={{ height }} className="shimmer rounded-xl" />;

  // downsample to ~160 points for smoothness
  const step = Math.max(1, Math.floor(points.length / 160));
  const pts = points.filter((_, i) => i % step === 0);
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const range = max - min || 1;
  const pad = 8;
  const x = (i: number) => (i / (pts.length - 1)) * W;
  const y = (v: number) => pad + (1 - (v - min) / range) * (H - pad * 2);

  const line = pts.map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L ${W} ${H} L 0 ${H} Z`;
  const last = pts[pts.length - 1];

  return (
    <div className="relative w-full" style={{ height }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full h-full overflow-visible">
        <defs>
          <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((g) => (
          <line key={g} x1="0" x2={W} y1={pad + g * (H - pad * 2)} y2={pad + g * (H - pad * 2)}
            stroke="var(--border)" strokeWidth="1" />
        ))}
        <motion.path d={area} fill="url(#areaFill)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8 }} />
        <motion.path d={line} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: "easeInOut" }} />
        <motion.circle cx={x(pts.length - 1)} cy={y(last)} r="4.5" fill="var(--accent)"
          initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 1.1, type: "spring" }} />
      </svg>
      <div className="absolute top-1 right-2 text-xs text-muted num">max {compactInr(max)}</div>
      <div className="absolute bottom-1 right-2 text-xs text-muted num">min {compactInr(min)}</div>
    </div>
  );
}

/* --------------------------------------------------------------- Donut */
export function Donut({ segments, size = 168 }: { segments: { label: string; value: number; color: string }[]; size?: number }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r = 58;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="flex items-center gap-5">
      <svg width={size} height={size} viewBox="0 0 140 140" className="-rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--panel-2)" strokeWidth="16" />
        {segments.map((s, i) => {
          const frac = s.value / total;
          const dash = frac * c;
          const el = (
            <motion.circle
              key={i} cx="70" cy="70" r={r} fill="none" stroke={s.color} strokeWidth="16" strokeLinecap="round"
              strokeDasharray={`${dash} ${c - dash}`}
              initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: -offset }}
              transition={{ delay: 0.15 * i, duration: 0.9, ease: "easeOut" }}
            />
          );
          offset += dash;
          return el;
        })}
      </svg>
      <div className="space-y-2">
        {segments.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-text-2">{s.label}</span>
            <span className="ml-auto num text-text-2">{compactInr(s.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
