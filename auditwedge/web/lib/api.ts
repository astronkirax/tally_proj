export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type Line = { group: string; ledger: string; amount: number };

export type AnalyzeResponse = {
  job_id: string;
  account: {
    bank: string;
    account_name: string | null;
    account_no: string | null;
    ifsc: string | null;
    from_date: string | null;
    to_date: string | null;
  };
  reconciliation: {
    opening: number;
    closing_computed: number;
    closing_reported: number | null;
    chains: boolean;
    drift: number;
    dr_count: number;
    cr_count: number;
    total_debits: number;
    total_credits: number;
    matches_summary: boolean | null;
    notes: string[];
  };
  stats: { total: number; classified: number; needs_review: number; rate: number };
  gateway_taxable: number;
  flags: {
    severity: "high" | "medium" | "low";
    code: string;
    title: string;
    detail: string;
    amount: number | null;
    row: number | null;
    date: string | null;
  }[];
  transactions: {
    row: number;
    date: string;
    narration: string;
    ref: string | null;
    debit: number | null;
    credit: number | null;
    balance: number;
    ledger: string;
    counterparty: string | null;
    type: string | null;
    confidence: number;
    source: string;
    bucket: string | null;
  }[];
  has_masters: boolean;
  financials: {
    summary: Record<string, number | string[]>;
    pnl: { income: Line[]; expenses: Line[]; total_income: number; total_expense: number; net_profit: number };
    balance_sheet: {
      liabilities: Line[];
      assets: Line[];
      total_liabilities: number;
      total_assets: number;
      suspense: number;
    };
    cross_checks: { item: string; bank_or_invoice: number; masters: number | null; status: string }[];
  } | null;
  gst: {
    gstin: string;
    ret_period: string;
    intra_state: boolean;
    cab: GstScenario;
    commission: GstScenario;
  } | null;
  itr: {
    form: string;
    assessment_year: string;
    financial_year: string;
    pl: Record<string, number>;
    bs: Record<string, number>;
    computation: Record<string, number | string>;
  } | null;
};

export type GstScenario = {
  label: string;
  taxable: number;
  rate: number;
  igst: number;
  cgst: number;
  sgst: number;
  total_tax: number;
};

export async function analyze(form: FormData): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export function downloadUrl(jobId: string, artifact: string): string {
  return `${API_BASE}/api/download/${jobId}/${artifact}`;
}

export function mastersTemplateUrl(example = false): string {
  return `${API_BASE}/api/templates/masters${example ? "?example=true" : ""}`;
}
