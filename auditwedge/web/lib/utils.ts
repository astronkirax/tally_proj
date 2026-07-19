import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function inr(n: number | null | undefined, dp = 2): string {
  if (n === null || n === undefined) return "—";
  return (
    "₹" +
    n.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp })
  );
}

export function compactInr(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e7) return "₹" + (n / 1e7).toFixed(2) + " Cr";
  if (abs >= 1e5) return "₹" + (n / 1e5).toFixed(2) + " L";
  if (abs >= 1e3) return "₹" + (n / 1e3).toFixed(1) + "K";
  return inr(n, 0);
}
