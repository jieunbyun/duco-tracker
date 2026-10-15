// Dates are plain "YYYY-MM-DD" strings in the diary's own calendar. Timestamps
// in the database hold wall-clock time labelled UTC (see 0001_schema.sql), so
// a calendar day here is the same day the database reports.

export type Range = { from: string; to: string };

export function iso(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function parse(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function addDays(s: string, n: number): string {
  const d = parse(s);
  d.setDate(d.getDate() + n);
  return iso(d);
}

export function today(): string {
  return iso(new Date());
}

// First day of the week (0 = Sunday … 6 = Saturday), from user_setting.
// Set once the settings load; Monday until then.
let weekStartDay = 1;
export function setWeekStartDay(day: number) {
  if (Number.isInteger(day) && day >= 0 && day <= 6) weekStartDay = day;
}
export function getWeekStartDay(): number {
  return weekStartDay;
}

/** First day of the week containing s. */
export function weekStart(s: string): string {
  const d = parse(s);
  return addDays(s, -((d.getDay() - weekStartDay + 7) % 7));
}

/** Inclusive day count. */
export function daysIn(r: Range): number {
  return Math.round((parse(r.to).getTime() - parse(r.from).getTime()) / 86_400_000) + 1;
}

export function fmtDay(s: string): string {
  return parse(s).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export type Preset = "this-week" | "last-week" | "this-month" | "year-to-date" | "last-12-months" | "custom";

export const PRESETS: { key: Preset; label: string }[] = [
  { key: "this-week", label: "This week" },
  { key: "last-week", label: "Last week" },
  { key: "this-month", label: "This month" },
  { key: "year-to-date", label: "Year to date" },
  { key: "last-12-months", label: "Last 12 months" },
  { key: "custom", label: "Custom" },
];

export function presetRange(p: Preset, custom: Range): Range {
  const t = today();
  switch (p) {
    case "this-week": {
      const from = weekStart(t);
      return { from, to: addDays(from, 6) };
    }
    case "last-week": {
      const from = addDays(weekStart(t), -7);
      return { from, to: addDays(from, 6) };
    }
    case "this-month": {
      const d = parse(t);
      return { from: iso(new Date(d.getFullYear(), d.getMonth(), 1)),
               to: iso(new Date(d.getFullYear(), d.getMonth() + 1, 0)) };
    }
    case "year-to-date":
      return { from: `${t.slice(0, 4)}-01-01`, to: t };
    case "last-12-months":
      return { from: addDays(t, -364), to: t };
    case "custom":
      return custom;
  }
}
