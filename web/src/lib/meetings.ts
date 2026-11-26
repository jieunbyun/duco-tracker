// Meetings (0060_meetings.sql): your meeting logs, one series per log, as your .tex files
// kept them — and the way back to .tex, and in from it.
import { supabase } from "./supabase";
import { check } from "./data";
import { today, addDays } from "./dates";

/** `sent`: action lines sent to Week or ticked off; `done`: agenda items covered. */
export type Section = { heading: string; body: string; closed?: boolean; sent?: string[]; done?: string[] };
export type Series = { id: string; name: string; headings: string[]; project_id: string | null; created_at: string };
export type Meeting = {
  id: string; series_id: string; met_on: string; title: string | null; people: string | null;
  sections: Section[]; created_at: string; updated_at: string;
  todo_id?: string | null; // its entry on the Week calendar (0064)
};
export type MeetingFields = Pick<Meeting, "series_id" | "met_on" | "title" | "people" | "sections" | "todo_id">;

/** A meeting has its agenda (planned ahead), what was discussed, your actions and others', and your own observations. */
export const AGENDA = "Agenda";
export const DISCUSSION = "Discussion";
export const ACTIONS = "My actions";
export const OTHERS = "Others' actions";
export const OBSERVATIONS = "Observations";
/** A meeting's parts, in order. */
export const HEADINGS = [AGENDA, DISCUSSION, ACTIONS, OTHERS, OBSERVATIONS];
export const isObservations = (h: string) => h === OBSERVATIONS;
/** Your actions: each line can go to Week as a to-do. */
export const isAction = (h: string) => h === ACTIONS;
export const isOthers = (h: string) => h === OTHERS;
export const isAgenda = (h: string) => h === AGENDA;
/** Parts whose lines are tick boxes (`done` for the agenda, `sent` for actions: sent to Week or ticked off). */
export const tickField = (h: string): "done" | "sent" | null => (isAgenda(h) ? "done" : isAction(h) || isOthers(h) ? "sent" : null);
/** A section's lines, without their "- " (an empty or "N/A" line is no line). */
export const linesOf = (body: string) =>
  body.split("\n").map((l) => l.replace(/^\s*-\s*/, "").trim()).filter((l) => l && !/^n\/?a$/i.test(l));

/** "Purpose" + "Bi-weekly meeting." → "- Purpose: Bi-weekly meeting." (several lines: nested under it). */
function labelled(h: string, body: string): string {
  const lines = body.split("\n").filter((l) => l.trim());
  if (lines.length === 1) return `- ${h}: ${lines[0].replace(/^\s*-\s*/, "")}`;
  return [`- ${h}:`, ...lines.map((l) => `  ${/^\s*-\s/.test(l) ? l : `- ${l.trim()}`}`)].join("\n");
}
/**
 * Any meeting's sections as its five: Agenda; Discussion (and untitled notes; every other heading —
 * Purpose, Update, Decided, Open… — goes there as a labelled line); My actions (I will,
 * Actions, Next steps, To do); Others' actions (They will); and Observations, your own comments
 * (Impressions, Comments, Reflections). A "They will: …" line kept among the actions (as earlier
 * versions wrote them) moves to Others' actions.
 */
export function asTwo(sections: Section[]): Section[] {
  const discussion: string[] = [], actions: string[] = [], sent: string[] = [], agenda: string[] = [], done: string[] = [];
  const others: string[] = [], othersSent: string[] = [], observations: string[] = [];
  /** Lines of "They will: …" (or "- They will:" with lines nested under it) taken out of `body`. */
  const theirs = (body: string): string => {
    const keep: string[] = [];
    let nested = false;
    for (const l of body.split("\n")) {
      const m = l.match(/^\s*(?:-\s*)?they will:\s*(.*)$/i);
      if (m) { if (m[1].trim()) others.push(`- ${m[1].trim()}`); nested = !m[1].trim(); continue; }
      if (nested && /^\s{2,}\S/.test(l)) { others.push(l.replace(/^\s{2}/, "")); continue; }
      nested = false;
      keep.push(l);
    }
    return keep.join("\n");
  };
  for (const s of sections) {
    const h = s.heading.trim().replace(/[.:]\s*$/, "");
    const body = s.body.replace(/\s+$/, "");
    if (!linesOf(body).length) continue;
    if (/^agendas?$/i.test(h)) { agenda.push(body); done.push(...(s.done ?? [])); }
    else if (/^(actions?|my actions|i will|next steps|to ?dos?)$/i.test(h)) {
      const mine = theirs(body);
      if (linesOf(mine).length) actions.push(mine);
      sent.push(...(s.sent ?? []));
    }
    else if (/^(they will|others'? actions|their actions)$/i.test(h)) { others.push(body); othersSent.push(...(s.sent ?? [])); }
    else if (/^(observations?|impressions?|(my )?comments?|reflections?)$/i.test(h)) observations.push(body);
    else if (!h || /^(discussion|notes)$/i.test(h)) discussion.push(body);
    else discussion.push(labelled(h, body));
  }
  // put together from several headings: every line a bullet, so the list reads as one
  const join = (parts: string[]) => parts.length < 2 ? (parts[0] ?? "")
    : parts.join("\n").split("\n").filter((l) => l.trim()).map((l) => (/^\s*-\s/.test(l) ? l : `- ${l.trim()}`)).join("\n");
  return [
    { heading: AGENDA, body: join(agenda), ...(done.length ? { done } : {}) },
    { heading: DISCUSSION, body: join(discussion) },
    { heading: ACTIONS, body: join(actions), ...(sent.length ? { sent } : {}) },
    { heading: OTHERS, body: join(others), ...(othersSent.length ? { sent: othersSent } : {}) },
    { heading: OBSERVATIONS, body: join(observations) },
  ];
}

// ---- loading and saving ------------------------------------------------------------------
const PAGE = 1000;
const missing = (code?: string) => code === "PGRST205" || code === "42P01";

/** Every series and meeting; null until 0060 is run. */
export async function loadAll(): Promise<{ series: Series[]; meetings: Meeting[]; canLink: boolean } | null> {
  const s = await supabase.from("meeting_series").select("id,name,headings,project_id,created_at").order("name");
  if (s.error) {
    if (missing(s.error.code)) return null;
    throw new Error(s.error.message);
  }
  const meetings: Meeting[] = [];
  const COLS = "id,series_id,met_on,title,people,sections,created_at,updated_at";
  let canLink = true;
  for (let from = 0; ; from += PAGE) {
    const page = (cols: string) => supabase.from("meeting").select(cols)
      .order("met_on", { ascending: false }).order("created_at", { ascending: false }).order("id").range(from, from + PAGE - 1);
    let m = await page(canLink ? `${COLS},todo_id` : COLS);
    if (m.error && m.error.message.includes("todo_id")) { canLink = false; m = await page(COLS); } // 0064 not run yet
    if (m.error) throw new Error(m.error.message);
    meetings.push(...(m.data as unknown as Meeting[]).map((x) => ({ ...x, sections: asTwo(Array.isArray(x.sections) ? x.sections : []) })));
    if (m.data.length < PAGE) break;
  }
  return { series: s.data as Series[], meetings, canLink };
}
export async function saveSeries(id: string | null, fields: Partial<Pick<Series, "name" | "headings" | "project_id">>): Promise<string> {
  if (id) {
    await check(supabase.from("meeting_series").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("meeting_series").insert(fields).select("id").single());
  return row!.id;
}
export async function deleteSeries(id: string): Promise<void> {
  await check(supabase.from("meeting_series").delete().eq("id", id));
}
export async function saveMeeting(id: string | null, fields: Partial<MeetingFields>): Promise<string> {
  const at = { ...fields, updated_at: new Date().toISOString() };
  if (id) {
    await check(supabase.from("meeting").update(at).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("meeting").insert(at).select("id").single());
  return row!.id;
}
export async function deleteMeeting(id: string): Promise<void> {
  await check(supabase.from("meeting").delete().eq("id", id));
}
/** A whole log at once: the series and all its meetings. */
export async function importLog(log: ParsedLog): Promise<string> {
  const id = await saveSeries(null, { name: log.name, headings: log.headings });
  if (log.meetings.length) {
    await check(supabase.from("meeting").insert(log.meetings.map((m) => ({ ...m, series_id: id }))));
  }
  return id;
}
/** A line of an action section, as a to-do in Week (filed under the week of `day`). */
export async function sendToWeek(title: string, note: string, day = today()): Promise<void> {
  await check(supabase.from("todo").insert({ kind: "task", title, due_on: day, note }));
}

// ---- the Week calendar ------------------------------------------------------------------
/** A meeting on the Week calendar: its to-do, and the day and times it is planned. */
export type CalendarEntry = { todo_id: string; title: string; day: string; start: string | null; end: string | null; source: string | null };

/** The calendar's meetings (kind "meeting") with a day from `from` to `to`, by day and time. */
export async function calendarBetween(from: string, to: string): Promise<CalendarEntry[]> {
  const slots = await check<{ todo_id: string; planned_on: string; start_time: string | null; end_time: string | null; is_cancelled: boolean }[]>(
    supabase.from("todo_slot").select("todo_id,planned_on,start_time,end_time,is_cancelled").gte("planned_on", from).lte("planned_on", to));
  const ids = [...new Set((slots ?? []).filter((x) => !x.is_cancelled).map((x) => x.todo_id))];
  if (!ids.length) return [];
  const todos = await check<{ id: string; title: string; kind: string; source: string | null; is_cancelled: boolean }[]>(
    supabase.from("todo").select("id,title,kind,source,is_cancelled").in("id", ids));
  const meeting = new Map((todos ?? []).filter((t) => t.kind === "meeting" && !t.is_cancelled).map((t) => [t.id, t]));
  return (slots ?? []).filter((x) => !x.is_cancelled && meeting.has(x.todo_id))
    .map((x) => ({ todo_id: x.todo_id, title: meeting.get(x.todo_id)!.title, day: x.planned_on, start: x.start_time, end: x.end_time, source: meeting.get(x.todo_id)!.source }))
    .sort((a, b) => a.day.localeCompare(b.day) || (a.start ?? "").localeCompare(b.start ?? ""));
}
/** Where the given calendar meetings are (their first day planned): todo id → entry. */
export async function calendarFor(todoIds: string[]): Promise<Map<string, CalendarEntry>> {
  const out = new Map<string, CalendarEntry>();
  if (!todoIds.length) return out;
  const [todos, slots] = await Promise.all([
    check<{ id: string; title: string; source: string | null }[]>(supabase.from("todo").select("id,title,source").in("id", todoIds)),
    check<{ todo_id: string; planned_on: string; start_time: string | null; end_time: string | null }[]>(
      supabase.from("todo_slot").select("todo_id,planned_on,start_time,end_time").in("todo_id", todoIds).order("planned_on")),
  ]);
  for (const t of todos ?? []) {
    const x = (slots ?? []).find((y) => y.todo_id === t.id);
    if (x) out.set(t.id, { todo_id: t.id, title: t.title, day: x.planned_on, start: x.start_time, end: x.end_time, source: t.source });
  }
  return out;
}
/** A new meeting on the Week calendar, on `day` from `start` to `end` ("HH:MM"); its to-do's id. */
export async function addToCalendar(title: string, day: string, start: string, end: string): Promise<string> {
  const todo = await check<{ id: string }>(supabase.from("todo").insert({ kind: "meeting", title, due_on: day }).select("id").single());
  await check(supabase.from("todo_slot").insert({ todo_id: todo!.id, planned_on: day, start_time: start || null, end_time: end || null }));
  return todo!.id;
}
/** For Week: which of its calendar meetings have a meeting log here — todo id → meeting id. Empty until 0064 is run. */
export async function agendasFor(todoIds: string[]): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  if (!todoIds.length) return out;
  const r = await supabase.from("meeting").select("id,todo_id").in("todo_id", todoIds);
  if (r.error) return out;
  for (const m of r.data as { id: string; todo_id: string }[]) out.set(m.todo_id, m.id);
  return out;
}
/** Week's address for a calendar meeting: its week, with the meeting picked out. */
export const weekHash = (day: string, todoId: string, weekStartOf: (d: string) => string) =>
  `#/week?w=${weekStartOf(day)}&show=${todoId}`;
export const soon = (day: string) => day >= today() && day <= addDays(today(), 14);

// ---- from .tex ---------------------------------------------------------------------------
export type ParsedMeeting = Omit<MeetingFields, "series_id">;
export type ParsedLog = { name: string; headings: string[]; meetings: ParsedMeeting[]; skipped: string[] };

const unescape = (s: string) => s.replace(/\\([&%$#_{}])/g, "$1").replace(/~/g, " ");

/** LaTeX body text as plain lines: lists as "- " (nested "  - "), links as [text](url). */
function plain(tex: string): string {
  const out: string[] = [];
  let depth = 0;
  let line = "";
  const flush = () => {
    const t = line.replace(/\s+/g, " ").trim();
    if (t) out.push(depth ? `${"  ".repeat(depth - 1)}- ${t}` : t);
    line = "";
  };
  const text = tex
    .replace(/(^|[^\\])%.*$/gm, "$1") // comments
    .replace(/\\href\{([^}]*)\}\{([^}]*)\}/g, (_, url, label) => `[${label}](${url})`)
    .replace(/\\url\{([^}]*)\}/g, "$1")
    .replace(/\s*\\\\(\[[^\]]*\])?\s*/g, "\n\n"); // a forced line break: a line of its own
  for (const raw of text.split("\n")) {
    let rest = raw;
    // \begin{itemize}[...], and the same written without its \begin
    while (rest.trim()) {
      const begin = rest.match(/^\s*(?:\\begin)?\{(?:itemize|enumerate)\}(\[[^\]]*\])?/);
      const end = rest.match(/^\s*\\end\{(?:itemize|enumerate)\}/);
      const item = rest.match(/^\s*\\item\b\s?/);
      if (begin) { flush(); depth += 1; rest = rest.slice(begin[0].length); continue; }
      if (end) { flush(); depth = Math.max(0, depth - 1); rest = rest.slice(end[0].length); continue; }
      if (item) { flush(); rest = rest.slice(item[0].length); continue; }
      const next = rest.search(/\\item\b|\\end\{(?:itemize|enumerate)\}|\\begin\{(?:itemize|enumerate)\}/);
      const chunk = next > 0 ? rest.slice(0, next) : rest;
      line += ` ${chunk}`;
      rest = next > 0 ? rest.slice(next) : "";
    }
    if (!raw.trim() && !depth) flush(); // a blank line ends a paragraph
  }
  flush();
  return unescape(out.join("\n"));
}

/** "12-11-26. Title" → 2026-11-12 and "Title"; null without a date. */
function sectionHead(s: string): { met_on: string; title: string } | null {
  const m = s.trim().match(/^(\d{1,2})[-./](\d{1,2})[-./](\d{2}|\d{4})\.?\s*(.*)$/);
  if (!m) return null;
  const [, d, mo, y, rest] = m;
  const year = y.length === 2 ? `20${y}` : y;
  const iso = `${year}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
  if (Number.isNaN(Date.parse(iso)) || +mo > 12 || +d > 31) return null;
  return { met_on: iso, title: unescape(rest.replace(/\.\s*$/, "").trim()) };
}

/** A .tex meeting log, as your files are written: \section*{date. title}, \paragraph{Heading.}. */
export function parseTex(tex: string, fileName = ""): ParsedLog {
  const name = unescape(tex.match(/\\fancyhead\[R\]\{([^}]*)\}/)?.[1]?.trim()
    || fileName.replace(/\.tex$/i, "").replace(/^\d{4}\s+/, "").trim() || "Meetings");
  const body = tex.split(/\\begin\{document\}/)[1]?.split(/\\end\{document\}/)[0] ?? tex;
  const parts = body.split(/\\section\*?\{/).slice(1);
  const meetings: ParsedMeeting[] = [];
  const skipped: string[] = [];
  for (const part of parts) {
    // the section's title runs to its closing brace (titles may hold \& and the like)
    let i = 0, level = 1;
    for (; i < part.length && level; i++) {
      if (part[i] === "{" && part[i - 1] !== "\\") level++;
      if (part[i] === "}" && part[i - 1] !== "\\") level--;
    }
    const head = sectionHead(part.slice(0, i - 1));
    const rest = part.slice(i);
    if (!head) {
      skipped.push(part.slice(0, i - 1).trim() || "(untitled)");
      continue;
    }
    const sections: Section[] = [];
    const chunks = rest.split(/\\paragraph\*?\{/);
    const lead = plain(chunks[0]);
    if (lead) sections.push({ heading: "Notes", body: lead });
    for (const c of chunks.slice(1)) {
      const close = c.indexOf("}");
      const heading = unescape(c.slice(0, close).replace(/[.:]\s*$/, "").trim());
      const text = plain(c.slice(close + 1));
      if (!heading && !text) continue;
      sections.push({ heading: heading || "Notes", body: text });
    }
    meetings.push({ ...head, people: null, sections: asTwo(sections) });
  }
  return { name, headings: HEADINGS, meetings, skipped };
}

// ---- to .tex -----------------------------------------------------------------------------
/** Escapes what LaTeX would read as a command, but leaves your own \commands, and links, as they are. */
function esc(s: string): string {
  return s.split(/(\[[^\]]*\]\([^)]*\))/).map((part, i) => {
    if (i % 2) {
      const [, label, url] = part.match(/^\[([^\]]*)\]\(([^)]*)\)$/)!;
      return `\\href{${url}}{${esc(label)}}`;
    }
    return part.replace(/(^|[^\\])([&%$#_])/g, "$1\\$2");
  }).join("");
}
function texBody(body: string): string {
  const out: string[] = [];
  let depth = 0;
  const to = (d: number) => {
    while (depth < d) { out.push(`${"\t".repeat(depth)}\\begin{itemize}[nosep]`); depth++; }
    while (depth > d) { depth--; out.push(`${"\t".repeat(depth)}\\end{itemize}`); }
  };
  for (const raw of body.split("\n")) {
    if (!raw.trim()) continue;
    const m = raw.match(/^(\s*)-\s+(.*)$/);
    if (m) {
      to(Math.floor(m[1].replace(/\t/g, "  ").length / 2) + 1);
      out.push(`${"\t".repeat(depth)}\\item ${esc(m[2])}`);
    } else {
      to(0);
      // a line after a line: a forced break, so the two don't run together
      if (out.length && !out[out.length - 1].trim().startsWith("\\")) out[out.length - 1] += " \\\\";
      out.push(esc(raw.trim()));
    }
  }
  to(0);
  return out.join("\n");
}
const dmy = (iso: string) => `${iso.slice(8, 10)}-${iso.slice(5, 7)}-${iso.slice(2, 4)}`;

/** A series as a .tex file, laid out as yours are: newest meeting first. */
export function toTex(series: Series, meetings: Meeting[]): string {
  const out = [
    "\\documentclass[final,11pt]{article}", "",
    "\\usepackage[margin=2.5cm]{geometry}", "\\usepackage{fancyhdr}", "\\usepackage{parskip,hyperref,enumitem}", "",
    "\\pagestyle{fancy}", "\\fancyhf{}", "\\fancyhead[L]{Meeting notes}", `\\fancyhead[R]{${esc(series.name)}}`, "",
    "\\begin{document}", "",
  ];
  for (const m of [...meetings].sort((a, b) => b.met_on.localeCompare(a.met_on))) {
    const title = [m.title?.trim(), m.people?.trim() ? `(${m.people.trim()})` : ""].filter(Boolean).join(" ");
    out.push(`\\section*{${dmy(m.met_on)}.${title ? ` ${esc(title)}` : ""}}`, "");
    for (const s of m.sections) {
      if (!s.body.trim()) continue;
      const body = texBody(s.body);
      out.push(body.startsWith("\\begin") ? `\\paragraph{${esc(s.heading)}.}\n${body}` : `\\paragraph{${esc(s.heading)}.} ${body}`, "");
    }
  }
  out.push("\\end{document}", "");
  return out.join("\n");
}
export function downloadTex(fileName: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "application/x-tex" }));
  a.download = fileName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
