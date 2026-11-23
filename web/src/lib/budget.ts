// Budget (0061_budget.sql): grant and project budgets — lines with a plan and an account
// code, and the expenses that add up to what is used and what remains.
import { supabase } from "./supabase";
import { check } from "./data";
import { at, text, excelDate, terms, type Sheet } from "./xlsx";

export type Budget = {
  id: string; name: string; total: number | null; currency: string; starts_on: string | null; ends_on: string | null;
  project_id: string | null; notes: string | null; created_at: string;
};
export type Line = { id: string; budget_id: string; name: string; plan: number | null; account: string | null; sort_order: number };
export type Expense = {
  id: string; budget_id: string; line_id: string | null; spent_on: string | null; amount: number;
  item: string | null; detail: string | null; created_at: string;
};
export type BudgetFields = Omit<Budget, "id" | "created_at">;
export type LineFields = Omit<Line, "id">;
export type ExpenseFields = Omit<Expense, "id" | "created_at">;

const missing = (code?: string) => code === "PGRST205" || code === "42P01";
const num = (v: unknown) => (v === null || v === undefined || v === "" ? null : +v);

/** Every budget with its lines and expenses; null until 0061 is run. */
export async function loadBudgets(): Promise<{ budgets: Budget[]; lines: Line[]; expenses: Expense[] } | null> {
  const b = await supabase.from("budget").select("*").order("created_at");
  if (b.error) {
    if (missing(b.error.code)) return null;
    throw new Error(b.error.message);
  }
  const [l, e] = await Promise.all([
    supabase.from("budget_line").select("id,budget_id,name,plan,account,sort_order").order("sort_order").order("created_at"),
    supabase.from("budget_expense").select("*").order("spent_on", { ascending: false, nullsFirst: false }).order("created_at", { ascending: false }),
  ]);
  for (const r of [l, e]) if (r.error) throw new Error(r.error.message);
  return {
    budgets: (b.data as Budget[]).map((x) => ({ ...x, total: num(x.total) })),
    lines: (l.data as Line[]).map((x) => ({ ...x, plan: num(x.plan) })),
    expenses: (e.data as Expense[]).map((x) => ({ ...x, amount: +x.amount })),
  };
}

async function upsert<T extends object>(table: string, id: string | null, fields: T): Promise<string> {
  if (id) {
    await check(supabase.from(table).update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from(table).insert(fields).select("id").single());
  return row!.id;
}
export const saveBudget = (id: string | null, f: Partial<BudgetFields>) => upsert("budget", id, f);
export const saveLine = (id: string | null, f: Partial<LineFields>) => upsert("budget_line", id, f);
export const saveExpense = (id: string | null, f: Partial<ExpenseFields>) => upsert("budget_expense", id, f);
export async function remove(table: "budget" | "budget_line" | "budget_expense", id: string): Promise<void> {
  await check(supabase.from(table).delete().eq("id", id));
}

/** Money, as the sheet would show it: "£1,425.50" (whole pounds without pence). */
export function money(n: number | null | undefined, currency = "£"): string {
  if (n === null || n === undefined) return "–";
  const neg = n < 0;
  const s = Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: Number.isInteger(Math.round(Math.abs(n) * 100) / 100) ? 0 : 2, maximumFractionDigits: 2 });
  return `${neg ? "−" : ""}${currency}${s}`;
}

// ---- from a spreadsheet laid out as yours: a header row with Plan and Used, the lines below
// it down to Sum (the total), and further down a table with Amount and Date (the expenses) ----
export type ParsedExpense = { spent_on: string | null; amount: number; item: string | null; detail: string | null };
export type ParsedLine = { name: string; plan: number | null; account: string | null; expenses: ParsedExpense[]; sheetUsed: number | null };
export type ParsedBudget = { sheet: string; name: string; total: number | null; lines: ParsedLine[]; unassigned: ParsedExpense[]; notes: string[] };

const find = (s: Sheet, row: number, re: RegExp) => {
  for (let c = 1; c <= s.maxCol; c++) if (re.test(text(at(s, row, c)))) return c;
  return 0;
};
const value = (s: Sheet, row: number, col: number): number | null => {
  const v = col ? at(s, row, col)?.v : null;
  return typeof v === "number" ? v : null;
};

export function parseBudgets(sheets: Sheet[]): ParsedBudget[] {
  const out: ParsedBudget[] = [];
  for (const s of sheets) {
    let head = 0;
    for (let r = 1; r <= s.maxRow && !head; r++) if (find(s, r, /^plan(ned)?$/i) && find(s, r, /^used|spent$/i)) head = r;
    if (!head) continue;
    const cPlan = find(s, head, /^plan(ned)?$/i), cUsed = find(s, head, /^used|spent$/i);
    const cAccount = find(s, head, /account|code/i), cUpdate = find(s, head, /last update|updated/i);
    const notes: string[] = [];
    const lines: ParsedLine[] = [];
    let total: number | null = null;
    let r = head + 1;
    for (let blank = 0; r <= s.maxRow && blank < 2; r++) {
      const name = text(at(s, r, 1));
      if (!name) { blank++; continue; }
      blank = 0;
      if (/^(sum|total)$/i.test(name)) { total = value(s, r, cPlan); continue; }
      if (/^remaining$/i.test(name)) continue;
      if (/^(detail|item)/i.test(name)) break; // the expenses table
      const used = at(s, r, cUsed);
      const day = value(s, r, cUpdate);
      const expenses: ParsedExpense[] = [];
      // what is used, written as sums of numbers ("=425+450+450+100"): one expense a number
      const parts = used?.f ? terms(used.f) : typeof used?.v === "number" ? [used.v] : null;
      if (parts) {
        for (const a of parts) expenses.push({ spent_on: day ? excelDate(day) : null, amount: Math.round(a * 100) / 100, item: "From the spreadsheet", detail: null });
      }
      lines.push({ name, plan: value(s, r, cPlan), account: text(at(s, r, cAccount)) || null, expenses, sheetUsed: typeof used?.v === "number" ? used.v : null });
    }
    // the expenses table
    const unassigned: ParsedExpense[] = [];
    let eh = 0;
    for (let x = head + 1; x <= s.maxRow && !eh; x++) if (find(s, x, /^amount$/i) && find(s, x, /^date$/i)) eh = x;
    if (eh) {
      const cAmount = find(s, eh, /^amount$/i), cDate = find(s, eh, /^date$/i), cCat = find(s, eh, /^(category|line)$/i);
      const cItem = find(s, eh, /^(detail\s*1|item|what)$/i) || 1, cDetail = find(s, eh, /^(detail\s*2|detail|note)$/i);
      for (let x = eh + 1; x <= s.maxRow; x++) {
        const amount = value(s, x, cAmount);
        if (amount === null) continue;
        const d = value(s, x, cDate);
        const e = { spent_on: d ? excelDate(d) : null, amount, item: text(at(s, x, cItem)) || null, detail: cDetail ? text(at(s, x, cDetail)) || null : null };
        const cat = text(at(s, x, cCat)).toLowerCase();
        const line = cat ? lines.find((l) => l.name.toLowerCase() === cat)
          ?? lines.find((l) => l.name.toLowerCase().startsWith(cat) || cat.startsWith(l.name.toLowerCase())) : undefined;
        (line ? line.expenses : unassigned).push(e);
      }
    }
    // check what was read against what the sheet shows as used
    for (const l of lines) {
      const sum = l.expenses.reduce((a, e) => a + e.amount, 0);
      if (l.sheetUsed !== null && Math.abs(sum - l.sheetUsed) > 0.005) notes.push(`${l.name}: the sheet shows ${money(l.sheetUsed)} used; read ${money(sum)}.`);
    }
    const name = text(at(s, head, 1)) || s.name;
    out.push({ sheet: s.name, name, total, lines, unassigned, notes });
  }
  return out;
}

export async function importBudget(p: ParsedBudget): Promise<string> {
  const id = await saveBudget(null, { name: p.name, total: p.total, currency: "£" });
  let order = 0;
  const rows: Partial<ExpenseFields>[] = [];
  for (const l of p.lines) {
    const line = await saveLine(null, { budget_id: id, name: l.name, plan: l.plan, account: l.account, sort_order: (order += 10) });
    rows.push(...l.expenses.map((e) => ({ ...e, budget_id: id, line_id: line })));
  }
  rows.push(...p.unassigned.map((e) => ({ ...e, budget_id: id, line_id: null })));
  if (rows.length) await check(supabase.from("budget_expense").insert(rows));
  return id;
}
