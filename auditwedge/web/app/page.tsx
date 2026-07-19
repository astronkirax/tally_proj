"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, ArrowRight, CheckCircle2, Download, FileSpreadsheet, FileText,
  Landmark, LayoutDashboard, Receipt, ScrollText, Sparkles, Upload, X,
} from "lucide-react";
import { useRef, useState } from "react";
import { BalanceArea, Donut } from "@/components/charts";
import { Badge, Button, Card, CountUp, StatTile, ThemeToggle } from "@/components/ui";
import { analyze, AnalyzeResponse, downloadUrl, mastersTemplateUrl } from "@/lib/api";
import { cn, compactInr, inr } from "@/lib/utils";

const STAGES = ["Reading statement", "Reconciling", "Classifying", "Scanning red flags", "Building financials"];
const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "vouchers", label: "Tally vouchers", icon: Receipt },
  { id: "financials", label: "Financials", icon: FileSpreadsheet, m: true },
  { id: "gst", label: "GST", icon: Landmark, m: true },
  { id: "itr", label: "Income tax", icon: ScrollText, m: true },
  { id: "flags", label: "Red flags", icon: AlertTriangle },
];

export default function Page() {
  const [pdf, setPdf] = useState<File | null>(null);
  const [invoices, setInvoices] = useState<File | null>(null);
  const [masters, setMasters] = useState<File | null>(null);
  const [useLlm, setUseLlm] = useState(true);
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [res, setRes] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState("overview");

  async function run() {
    if (!pdf) return;
    setLoading(true); setError(null); setRes(null);
    const t = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 1400);
    try {
      const fd = new FormData();
      fd.append("statement", pdf);
      if (invoices) fd.append("invoices", invoices);
      if (masters) fd.append("masters", masters);
      fd.append("use_llm", String(useLlm));
      fd.append("password", password);
      const r = await analyze(fd);
      setRes(r); setSection("overview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      clearInterval(t); setStage(0); setLoading(false);
    }
  }

  return (
    <div className="relative min-h-dvh overflow-hidden">
      <div className="orb h-[32rem] w-[32rem] -top-40 -right-32" style={{ background: "var(--accent)" }} />
      <div className="orb h-[26rem] w-[26rem] top-1/2 -left-40" style={{ background: "var(--accent-2)", animationDelay: "3s" }} />

      <div className="relative z-10 flex min-h-dvh">
        <Sidebar section={section} setSection={setSection} res={res} reset={() => { setRes(null); setPdf(null); }} />
        <main className="flex-1 min-w-0">
          <MobileBar />
          <div className="mx-auto max-w-5xl px-5 md:px-8 py-6 pb-24">
            <AnimatePresence mode="wait">
              {!res && !loading && (
                <Upload_ key="u" {...{ pdf, setPdf, invoices, setInvoices, masters, setMasters, useLlm, setUseLlm, password, setPassword, error, run }} />
              )}
              {loading && <Loading key="l" stage={stage} />}
              {res && !loading && (
                <Dashboard key="d" res={res} section={section} setSection={setSection} reset={() => { setRes(null); setPdf(null); }} />
              )}
            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  );
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--accent)] text-white glow">
        <ScrollText size={18} />
      </div>
      <div className="leading-tight">
        <div className="font-semibold tracking-tight">AuditWedge</div>
        <div className="text-[10px] text-muted">statement → filings</div>
      </div>
    </div>
  );
}

function Sidebar({ section, setSection, res, reset }: any) {
  return (
    <aside className="hidden lg:flex w-[262px] shrink-0 flex-col border-r border-border glass sticky top-0 h-dvh p-5">
      <Logo />
      <nav className="mt-9 flex-1 space-y-1">
        <div className="px-3 pb-2 text-[10px] uppercase tracking-widest text-muted">Workflow</div>
        {NAV.map((n) => {
          const has = !n.m || res?.has_masters;
          const clickable = !!res && has;
          const on = section === n.id && !!res;
          return (
            <button key={n.id} disabled={!clickable} onClick={() => clickable && setSection(n.id)}
              className={cn("group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                on ? "text-text" : clickable ? "text-muted hover:text-text" : "text-muted opacity-40 cursor-not-allowed")}>
              {on && <motion.div layoutId="navpill" className="absolute inset-0 rounded-xl bg-panel-2 border border-border" transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
              <span className={cn("relative z-10 grid h-7 w-7 place-items-center rounded-lg transition-colors", on ? "bg-[var(--accent)] text-white" : "bg-panel-2 text-muted group-hover:text-text-2")}>
                <n.icon size={15} />
              </span>
              <span className="relative z-10">{n.label}</span>
              {res && has && <CheckCircle2 size={14} className="relative z-10 ml-auto text-pos/70" />}
            </button>
          );
        })}
      </nav>
      <div className="mt-auto flex items-center justify-between border-t border-border pt-4">
        <ThemeToggle />
        {res ? (
          <button onClick={reset} className="text-xs text-muted hover:text-text transition-colors">New analysis</button>
        ) : (
          <span className="text-[10px] text-muted">v1.0</span>
        )}
      </div>
    </aside>
  );
}

function MobileBar() {
  return (
    <div className="lg:hidden sticky top-0 z-20 flex items-center justify-between border-b border-border glass px-5 py-3">
      <Logo />
      <ThemeToggle />
    </div>
  );
}

/* ------------------------------------------------------------- Upload */
function Upload_(p: any) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="relative pt-10">
      <div className="grid-fade pointer-events-none absolute inset-x-0 -top-10 h-72 opacity-60" />
      <div className="relative max-w-2xl">
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-panel px-3 py-1 text-xs text-text-2">
          <Sparkles size={12} className="text-accent" /> Reconciled to the rupee · Tally · GST · ITR
        </div>
        <h1 className="mt-5 text-[2.6rem] font-semibold leading-[1.05] tracking-tight gradient-text">
          A bank statement in.<br />Ready-to-file books out.
        </h1>
        <p className="mt-4 text-text-2 leading-relaxed">
          Vouchers, Profit &amp; Loss, Balance Sheet, GST and ITR — generated, cross-checked, and reconciled from one upload.
        </p>
      </div>

      <div className="relative mt-9">
        <BigDrop file={p.pdf} setFile={p.setPdf} />
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <SmallDrop label="Purchase invoices" hint="Excel · optional" file={p.invoices} setFile={p.setInvoices} accept=".xlsx" />
          <SmallDrop label="Client masters" hint="Excel · unlocks P&L / BS / GST / ITR" file={p.masters} setFile={p.setMasters} accept=".xlsx" />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
          <a className="text-accent hover:underline" href={mastersTemplateUrl(false)}>Blank masters template</a>
          <span className="text-muted">·</span>
          <a className="text-accent hover:underline" href={mastersTemplateUrl(true)}>Example (Gateway FY22-23)</a>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <input value={p.password} onChange={(e: any) => p.setPassword(e.target.value)} type="password" placeholder="PDF password (if locked)"
            className="rounded-xl border border-border bg-panel px-3 py-2.5 text-sm outline-none focus:border-[var(--accent)] w-52" />
          <button onClick={() => p.setUseLlm(!p.useLlm)}
            className={cn("inline-flex items-center gap-2 rounded-xl border px-3 py-2.5 text-sm transition-colors",
              p.useLlm ? "border-[var(--accent)] text-accent bg-[color-mix(in_oklab,var(--accent)_10%,transparent)]" : "border-border text-text-2")}>
            <Sparkles size={15} /> AI assist {p.useLlm ? "on" : "off"}
          </button>
          <Button onClick={p.run} className="ml-auto px-6 py-3 text-base" disabled={!p.pdf}>
            Analyze <ArrowRight size={18} />
          </Button>
        </div>

        {p.error && (
          <div className="mt-5 flex items-center gap-2 rounded-xl border border-[color-mix(in_oklab,var(--high)_35%,transparent)] bg-[color-mix(in_oklab,var(--high)_12%,transparent)] px-4 py-3 text-sm text-high">
            <AlertTriangle size={16} /> {p.error}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function BigDrop({ file, setFile }: any) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <motion.div whileHover={{ scale: 1.005 }} onClick={() => ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}
      className={cn("relative cursor-pointer overflow-hidden rounded-2xl border-2 border-dashed p-8 text-center transition-colors",
        over ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_7%,transparent)]" : "border-border-strong bg-panel/60",
        file && "border-solid border-[color-mix(in_oklab,var(--pos)_50%,transparent)] bg-[color-mix(in_oklab,var(--pos)_6%,transparent)]")}>
      <input ref={ref} type="file" accept=".pdf" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      {over && <div className="sheen pointer-events-none absolute inset-0" />}
      <div className="relative flex flex-col items-center gap-3">
        <div className={cn("grid h-14 w-14 place-items-center rounded-2xl", file ? "bg-[color-mix(in_oklab,var(--pos)_18%,transparent)] text-pos" : "bg-panel-2 text-accent")}>
          {file ? <CheckCircle2 size={26} /> : <Upload size={24} />}
        </div>
        {file ? (
          <div className="flex items-center gap-2 text-sm">
            <FileText size={15} className="text-text-2" /> <span className="font-medium">{file.name}</span>
            <button onClick={(e) => { e.stopPropagation(); setFile(null); }} className="text-muted hover:text-high"><X size={15} /></button>
          </div>
        ) : (
          <>
            <div className="text-base font-medium">Drop your bank statement</div>
            <div className="text-xs text-muted">PDF · HDFC &amp; KVB instant · any other bank via AI</div>
          </>
        )}
      </div>
    </motion.div>
  );
}

function SmallDrop({ label, hint, file, setFile, accept }: any) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div onClick={() => ref.current?.click()}
      onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}
      className={cn("card hover-lift cursor-pointer p-4 flex items-center gap-3", file && "border-[color-mix(in_oklab,var(--pos)_45%,transparent)]")}>
      <input ref={ref} type="file" accept={accept} className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <div className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg", file ? "bg-[color-mix(in_oklab,var(--pos)_18%,transparent)] text-pos" : "bg-panel-2 text-muted")}>
        {file ? <CheckCircle2 size={16} /> : <FileSpreadsheet size={16} />}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        <div className="truncate text-xs text-muted">{file ? file.name : hint}</div>
      </div>
      {file && <button onClick={(e) => { e.stopPropagation(); setFile(null); }} className="ml-auto text-muted hover:text-high"><X size={15} /></button>}
    </div>
  );
}

/* ------------------------------------------------------------- Loading */
function Loading({ stage }: { stage: number }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="pt-24">
      <div className="mx-auto max-w-md">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[var(--accent)] text-white glow">
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 2, ease: "linear" }}><Sparkles size={22} /></motion.div>
          </div>
          <div>
            <div className="font-medium">Processing your statement…</div>
            <div className="text-xs text-muted">Native banks are instant; AI-read banks take about a minute.</div>
          </div>
        </div>
        <div className="mt-8 space-y-3">
          {STAGES.map((s, i) => (
            <div key={s} className="flex items-center gap-3">
              <div className={cn("grid h-6 w-6 place-items-center rounded-full text-[11px] transition-colors", i < stage ? "bg-pos text-black" : i === stage ? "bg-[var(--accent)] text-white" : "bg-panel-2 text-muted")}>
                {i < stage ? <CheckCircle2 size={13} /> : i + 1}
              </div>
              <span className={cn("text-sm", i <= stage ? "text-text" : "text-muted")}>{s}</span>
              {i === stage && <div className="ml-2 h-1 flex-1 overflow-hidden rounded-full bg-panel-2"><motion.div className="h-full bg-[var(--accent)]" animate={{ width: ["8%", "92%"] }} transition={{ duration: 1.4, repeat: Infinity }} /></div>}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------- Dashboard */
function Dashboard({ res, section, setSection, reset }: any) {
  const r = res.reconciliation;
  const highs = res.flags.filter((f: any) => f.severity === "high").length;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-lg font-semibold">{res.account.account_name ?? "Statement"}</div>
          <div className="text-xs text-muted">{res.account.bank} · A/C {res.account.account_no} · {res.account.from_date} → {res.account.to_date}</div>
        </div>
        <Button variant="secondary" onClick={reset} className="hidden md:inline-flex">New analysis</Button>
      </div>

      {/* balance hero */}
      <Card className="p-5 hover-lift">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted">Account balance</div>
            <div className="mt-1 text-3xl font-semibold num"><CountUp value={r.closing_computed} prefix="₹" dp={2} /></div>
            <div className={cn("mt-1 inline-flex items-center gap-1.5 text-xs", r.chains ? "text-pos" : "text-high")}>
              <CheckCircle2 size={13} /> {r.chains ? "Reconciled · zero drift" : `Drift ${inr(r.drift)}`}
            </div>
          </div>
          <div className="text-right text-xs text-muted">
            <div>opening {compactInr(r.opening)}</div>
            <div className="mt-1">{res.transactions.length} transactions</div>
          </div>
        </div>
        <div className="mt-4"><BalanceArea points={res.transactions.map((t: any) => t.balance)} /></div>
      </Card>

      {/* KPIs */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <StatTile label="Money in" tone="pos" value={<CountUp value={r.total_credits} prefix="₹" dp={0} />} sub={`${r.cr_count} receipts`} />
        <StatTile label="Money out" tone="neg" value={<CountUp value={r.total_debits} prefix="₹" dp={0} />} sub={`${r.dr_count} payments`} />
        <StatTile label={res.has_masters ? "Net profit" : "Net change"} tone="accent"
          value={<CountUp value={res.financials ? res.financials.pnl.net_profit : r.total_credits - r.total_debits} prefix="₹" dp={0} />} />
        <StatTile label="Red flags" tone={highs ? "neg" : "default"} value={<CountUp value={res.flags.length} />} sub={`${highs} high`} />
      </div>

      {/* mobile section pills */}
      <div className="lg:hidden -mx-5 overflow-x-auto px-5">
        <div className="flex gap-1 rounded-xl border border-border bg-panel p-1 w-max">
          {NAV.filter((n) => !n.m || res.has_masters).map((n) => (
            <button key={n.id} onClick={() => setSection(n.id)} className={cn("whitespace-nowrap rounded-lg px-3 py-1.5 text-sm", section === n.id ? "bg-panel-2 text-text" : "text-muted")}>{n.label}</button>
          ))}
        </div>
      </div>

      <Downloads res={res} />

      <AnimatePresence mode="wait">
        <motion.div key={section} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
          {section === "overview" && <Overview res={res} />}
          {section === "vouchers" && <Vouchers res={res} />}
          {section === "financials" && res.financials && <Financials res={res} />}
          {section === "gst" && res.gst && <Gst res={res} />}
          {section === "itr" && res.itr && <Itr res={res} />}
          {section === "flags" && <Flags res={res} />}
        </motion.div>
      </AnimatePresence>
    </motion.div>
  );
}

function Downloads({ res }: { res: AnalyzeResponse }) {
  const items = [
    { art: "workpaper", label: "Working paper", icon: FileSpreadsheet },
    { art: "tally", label: "Tally XML", icon: Receipt },
    { art: "vouchers", label: "Vouchers (Excel)", icon: FileText },
    ...(res.has_masters ? [
      { art: "gstr3b", label: "GSTR-3B", icon: Landmark },
      { art: "gstr1", label: "GSTR-1", icon: Landmark },
      { art: "itr", label: "ITR JSON", icon: ScrollText },
    ] : []),
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((it) => (
        <a key={it.art} href={downloadUrl(res.job_id, it.art)}
          className="group inline-flex items-center gap-2 rounded-xl border border-border bg-panel px-3 py-2 text-sm text-text-2 hover:text-text hover:border-[var(--accent)] transition-colors">
          <it.icon size={14} /> {it.label} <Download size={13} className="text-muted group-hover:text-accent" />
        </a>
      ))}
    </div>
  );
}

/* --------------------------------------------------------- sections */
function Overview({ res }: { res: AnalyzeResponse }) {
  const f = res.financials;
  const segments = f
    ? [
        { label: "Income", value: f.pnl.total_income, color: "var(--pos)" },
        { label: "Expenses", value: f.pnl.total_expense, color: "var(--neg)" },
      ]
    : [
        { label: "Receipts", value: res.reconciliation.total_credits, color: "var(--pos)" },
        { label: "Payments", value: res.reconciliation.total_debits, color: "var(--accent)" },
      ];
  const buckets = res.transactions.reduce((a: Record<string, number>, t) => { a[t.ledger] = (a[t.ledger] ?? 0) + (t.debit ?? t.credit ?? 0); return a; }, {});
  const rows = Object.entries(buckets).sort((x, y) => y[1] - x[1]).slice(0, 8);
  const max = rows[0]?.[1] ?? 1;
  return (
    <div className="grid gap-4 md:grid-cols-5">
      <Card className="p-5 md:col-span-2">
        <div className="text-sm font-medium mb-4">{f ? "Income vs expense" : "Receipts vs payments"}</div>
        <Donut segments={segments} />
      </Card>
      <Card className="p-5 md:col-span-3">
        <div className="text-sm font-medium mb-4">Top ledgers</div>
        <div className="space-y-3">
          {rows.map(([led, amt]) => (
            <div key={led} className="flex items-center gap-3">
              <div className="w-40 truncate text-sm text-text-2">{led}</div>
              <div className="flex-1 h-2 rounded-full bg-panel-2 overflow-hidden">
                <motion.div initial={{ width: 0 }} animate={{ width: `${(amt / max) * 100}%` }} transition={{ type: "spring", stiffness: 120, damping: 22 }} className="h-full rounded-full bg-[var(--accent)]" />
              </div>
              <div className="w-24 text-right text-sm num">{compactInr(amt)}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Vouchers({ res }: { res: AnalyzeResponse }) {
  const txns = res.transactions.slice(0, 400);
  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="text-sm font-medium">Vouchers <span className="text-muted">({res.transactions.length})</span></div>
        <span className="text-xs text-muted">Receipt / Payment · double-entry</span>
      </div>
      <div className="max-h-[520px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-panel-2 text-muted text-xs">
            <tr>{["#", "Date", "Narration", "Debit", "Credit", "Balance", "Ledger"].map((h) => (<th key={h} className="px-3 py-2.5 text-left font-medium first:pl-4">{h}</th>))}</tr>
          </thead>
          <tbody>
            {txns.map((t) => (
              <tr key={t.row} className="border-t border-border hover:bg-panel-2/60">
                <td className="px-3 py-2 pl-4 text-muted num">{t.row}</td>
                <td className="px-3 py-2 whitespace-nowrap text-text-2">{t.date}</td>
                <td className="px-3 py-2 max-w-xs truncate" title={t.narration}>{t.narration}</td>
                <td className="px-3 py-2 num text-neg">{t.debit ? inr(t.debit, 0) : ""}</td>
                <td className="px-3 py-2 num text-pos">{t.credit ? inr(t.credit, 0) : ""}</td>
                <td className="px-3 py-2 num text-text-2">{inr(t.balance, 0)}</td>
                <td className="px-3 py-2 text-xs text-text-2">{t.ledger}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {res.transactions.length > 400 && <div className="px-4 py-2 text-xs text-muted border-t border-border">Showing 400 of {res.transactions.length} — full set in the Vouchers Excel / Tally XML.</div>}
    </Card>
  );
}

function LedgerList({ title, lines, total }: { title: string; lines: any[]; total: number }) {
  const groups = lines.reduce((a: Record<string, any[]>, l) => { (a[l.group] ??= []).push(l); return a; }, {});
  return (
    <Card className="p-5">
      <div className="text-sm font-medium mb-3">{title}</div>
      <div className="space-y-3">
        {Object.entries(groups).map(([g, ls]) => (
          <div key={g}>
            <div className="text-[11px] uppercase tracking-wider text-muted">{g}</div>
            {(ls as any[]).map((l, i) => (
              <div key={i} className="flex justify-between py-1 text-sm"><span className="text-text-2 pl-2">{l.ledger}</span><span className="num">{inr(l.amount)}</span></div>
            ))}
          </div>
        ))}
        <div className="flex justify-between border-t border-border pt-2 text-sm font-semibold"><span>Total</span><span className="num">{inr(total)}</span></div>
      </div>
    </Card>
  );
}

function Financials({ res }: { res: AnalyzeResponse }) {
  const f = res.financials!;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <StatTile label="Net profit" tone="pos" value={<CountUp value={f.pnl.net_profit} prefix="₹" dp={2} />} />
        <StatTile label="Balance sheet total" value={<CountUp value={f.balance_sheet.total_assets} prefix="₹" dp={2} />} />
        <StatTile label="Suspense plug" tone={f.balance_sheet.suspense === 0 ? "pos" : "neg"} value={<CountUp value={f.balance_sheet.suspense} prefix="₹" dp={2} />} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <LedgerList title="Profit & Loss" lines={[...f.pnl.income, ...f.pnl.expenses]} total={f.pnl.total_income} />
        <LedgerList title="Balance Sheet" lines={[...f.balance_sheet.liabilities, ...f.balance_sheet.assets]} total={f.balance_sheet.total_assets} />
      </div>
      <Card className="p-5">
        <div className="text-sm font-medium mb-3">Cross-checks (bank / invoices vs books)</div>
        {f.cross_checks.map((c, i) => (
          <div key={i} className="flex items-center justify-between py-1.5 text-sm border-t border-border first:border-0">
            <span className="text-text-2">{c.item}</span>
            <span className="flex items-center gap-3"><span className="num">{inr(c.bank_or_invoice)}</span>{c.status.includes("review") ? <Badge tone="medium">{c.status}</Badge> : <Badge tone="pos">ok</Badge>}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}

function Gst({ res }: { res: AnalyzeResponse }) {
  const g = res.gst!;
  return (
    <Card className="p-5">
      <div className="text-xs text-muted mb-4">GSTIN {g.gstin} · period {g.ret_period} · {g.intra_state ? "intra-state (CGST+SGST)" : "inter-state (IGST)"}</div>
      <div className="grid gap-3 md:grid-cols-2">
        {[g.cab, g.commission].map((sc, i) => (
          <div key={i} className="rounded-xl border border-border p-4 hover-lift">
            <div className="text-sm font-medium">{sc.label}</div>
            <div className="mt-3 text-3xl font-semibold text-accent num"><CountUp value={sc.total_tax} prefix="₹" dp={2} /></div>
            <div className="mt-3 grid grid-cols-2 gap-y-1 text-xs text-text-2">
              <span>Taxable</span><span className="text-right num">{inr(sc.taxable)}</span>
              <span>Rate</span><span className="text-right num">{sc.rate}%</span>
              <span>CGST</span><span className="text-right num">{inr(sc.cgst)}</span>
              <span>SGST</span><span className="text-right num">{inr(sc.sgst)}</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Itr({ res }: { res: AnalyzeResponse }) {
  const it = res.itr!;
  const block = (title: string, d: Record<string, any>) => (
    <Card className="p-5">
      <div className="text-sm font-medium mb-3">{title}</div>
      {Object.entries(d).map(([k, v]) => (
        <div key={k} className="flex justify-between py-1 text-sm border-t border-border first:border-0">
          <span className="text-text-2 capitalize">{k.replace(/_/g, " ")}</span>
          <span className="num text-right max-w-[55%] truncate">{typeof v === "number" ? inr(v) : String(v)}</span>
        </div>
      ))}
    </Card>
  );
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm"><Badge tone="pos">{it.form}</Badge><span className="text-muted">AY {it.assessment_year} · FY {it.financial_year}</span></div>
      <div className="grid gap-4 md:grid-cols-2">{block("P&L schedule", it.pl)}{block("Balance Sheet schedule", it.bs)}</div>
      {block("Computation of income & tax", it.computation)}
    </div>
  );
}

function Flags({ res }: { res: AnalyzeResponse }) {
  if (!res.flags.length) return <Card className="p-8 text-center text-muted">No exceptions raised.</Card>;
  return (
    <div className="space-y-2.5">
      {res.flags.map((f, i) => (
        <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}>
          <Card className="p-4">
            <div className="flex items-start gap-3">
              <Badge tone={f.severity}>{f.severity}</Badge>
              <div className="flex-1">
                <div className="text-sm font-medium">{f.title}{f.amount ? <span className="text-text-2 font-normal"> · {inr(f.amount)}</span> : null}</div>
                <div className="mt-1 text-xs text-text-2 leading-relaxed">{f.detail}</div>
              </div>
            </div>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}
