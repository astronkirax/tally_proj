"use client";

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ Button */
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};
export function Button({ className, variant = "primary", ...props }: BtnProps) {
  const styles = {
    primary:
      "bg-[var(--accent)] text-white hover:brightness-110 shadow-[0_6px_24px_-8px_var(--accent)]",
    secondary: "bg-panel-2 text-text border border-border-strong hover:bg-elevated",
    ghost: "text-text-2 hover:text-text hover:bg-panel-2",
  }[variant];
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium",
        "transition-colors disabled:opacity-40 disabled:pointer-events-none cursor-pointer select-none",
        styles,
        className
      )}
      {...(props as React.ComponentProps<typeof motion.button>)}
    />
  );
}

/* -------------------------------------------------------------------- Card */
export function Card({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("card shadow-[0_1px_2px_rgba(0,0,0,0.3)]", className)} {...props}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ CountUp */
export function CountUp({ value, prefix = "", suffix = "", dp = 0 }: { value: number; prefix?: string; suffix?: string; dp?: number }) {
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 90, damping: 20 });
  const text = useTransform(spring, (v) =>
    prefix + v.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp }) + suffix
  );
  useEffect(() => {
    mv.set(value);
  }, [value, mv]);
  return <motion.span className="num">{text}</motion.span>;
}

/* ----------------------------------------------------------------- StatTile */
export function StatTile({
  label,
  value,
  sub,
  tone = "default",
  icon,
  delay = 0,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "pos" | "neg" | "accent";
  icon?: React.ReactNode;
  delay?: number;
}) {
  const toneColor = {
    default: "text-text",
    pos: "text-pos",
    neg: "text-neg",
    accent: "text-accent",
  }[tone];
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 220, damping: 26 }}
      className="card p-5 relative overflow-hidden group"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
        {icon && <span className="text-muted group-hover:text-accent transition-colors">{icon}</span>}
      </div>
      <div className={cn("mt-2 text-2xl font-semibold num", toneColor)}>{value}</div>
      {sub && <div className="mt-1 text-xs text-text-2">{sub}</div>}
    </motion.div>
  );
}

/* ------------------------------------------------------------------- Badge */
export function Badge({ tone = "low", children }: { tone?: "high" | "medium" | "low" | "pos" | "muted"; children: React.ReactNode }) {
  const map = {
    high: "bg-[color-mix(in_oklab,var(--high)_18%,transparent)] text-high border-[color-mix(in_oklab,var(--high)_35%,transparent)]",
    medium: "bg-[color-mix(in_oklab,var(--medium)_16%,transparent)] text-medium border-[color-mix(in_oklab,var(--medium)_35%,transparent)]",
    low: "bg-[color-mix(in_oklab,var(--low)_15%,transparent)] text-low border-[color-mix(in_oklab,var(--low)_32%,transparent)]",
    pos: "bg-[color-mix(in_oklab,var(--pos)_15%,transparent)] text-pos border-[color-mix(in_oklab,var(--pos)_32%,transparent)]",
    muted: "bg-panel-2 text-muted border-border",
  }[tone];
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", map)}>
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- Skeleton */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-lg", className)} />;
}

/* -------------------------------------------------------------- ThemeToggle */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const isDark = theme !== "light";
  return (
    <button
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="grid h-9 w-9 place-items-center rounded-xl border border-border text-text-2 hover:text-text hover:bg-panel-2 transition-colors cursor-pointer"
    >
      {mounted ? (isDark ? <Sun size={16} /> : <Moon size={16} />) : <Sun size={16} />}
    </button>
  );
}
