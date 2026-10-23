// Outlook → the plan. The calendar-sync function hands over your published
// calendar; everything else happens here, as you (row-level security applies).
//
// Each Outlook occurrence becomes a to-do (a meeting, or a task for an all-day
// event) with one sitting, marked unreviewed until you keep it. Later syncs:
//   - new in Outlook            → added, unreviewed
//   - moved/renamed in Outlook   → follows, unless that sitting is logged
//   - gone/cancelled in Outlook  → removed if unreviewed; if kept, cancelled
//                                  (struck through) unless already logged, and
//                                  restored if it comes back — but a sitting
//                                  you cancelled yourself stays cancelled
//   - marked irrelevant here     → removed and never brought back
import { supabase } from "./supabase";
import { check, TODO_COLS, SLOT_COLS, asTodo, asSlot, saveTodo, saveSlot, deleteTodo } from "./data";
import type { Todo, Slot } from "./data";
import { meetingsInRange, eventUids } from "./ics";
import type { Meeting } from "./ics";
import { addDays, today, weekStart } from "./dates";

// The Edge Function's address (its slug), which the dashboard may choose for
// you when deploying; set VITE_CALENDAR_FUNCTION when it is not "calendar-sync".
const CALENDAR_FUNCTION = (import.meta.env.VITE_CALENDAR_FUNCTION as string | undefined)?.trim() || "calendar-sync";

/** How far ahead to bring events in, in weeks from the start of this week. */
export const RANGES = [
  { weeks: 1, label: "This week" },
  { weeks: 2, label: "This and next week" },
  { weeks: 4, label: "Next 4 weeks" },
  { weeks: 13, label: "Next 3 months" },
];
export function syncWindow(weeks: number): { from: string; to: string } {
  const from = weekStart(today());
  return { from, to: addDays(from, 7 * Math.max(1, weeks) - 1) };
}
export const STALE_HOURS = 3;

export type Feed = { ics_url: string | null; last_synced_at: string | null; last_status: string | null; sync_weeks: number };
export type Ignore = { id: string; uid: string; occurrence: string | null; title: string | null };
export type SyncResult = { added: number; updated: number; removed: number; skipped: number; cleared: number };

export async function loadFeed(): Promise<Feed | null> {
  const full = await supabase.from("calendar_feed").select("ics_url,last_synced_at,last_status,sync_weeks").maybeSingle();
  if (!full.error) return full.data ? { ...full.data, sync_weeks: Number(full.data.sync_weeks ?? 1) } : null;
  // before 0006_outlook_range.sql: no range column yet, so this week only
  const basic = await check<Omit<Feed, "sync_weeks">>(
    supabase.from("calendar_feed").select("ics_url,last_synced_at,last_status").maybeSingle());
  return basic ? { ...basic, sync_weeks: 1 } : null;
}
export async function saveFeed(fields: { ics_url: string | null; sync_weeks: number }): Promise<void> {
  await check(supabase.from("calendar_feed").upsert({ ics_url: fields.ics_url?.trim() || null, sync_weeks: fields.sync_weeks }));
}
async function saveFeedStatus(status: string): Promise<void> {
  await check(supabase.from("calendar_feed").update({ last_synced_at: new Date().toISOString(), last_status: status }).not("user_id", "is", null));
}

export async function loadIgnores(): Promise<Ignore[]> {
  return (await check<Ignore[]>(supabase.from("calendar_ignore").select("id,uid,occurrence,title").order("created_at"))) ?? [];
}
/** Never bring this occurrence back (occurrence = its key), or any of the series (null). */
export async function addIgnore(uid: string, occurrence: string | null, title: string): Promise<string> {
  const row = await check<{ id: string }>(
    supabase.from("calendar_ignore").insert({ uid, occurrence, title }).select("id").single(),
  );
  return row!.id;
}
export async function removeIgnore(id: string): Promise<void> {
  await check(supabase.from("calendar_ignore").delete().eq("id", id));
}

/** Outlook to-dos waiting to be kept or dismissed, soonest first. */
export async function loadUnreviewed(): Promise<{ todos: Todo[]; slots: Slot[] }> {
  const todos = ((await check<Todo[]>(
    supabase.from("todo").select(TODO_COLS).eq("source", "outlook").eq("reviewed", false)
      .order("due_on").order("source_start"),
  )) ?? []).map(asTodo);
  const slots = todos.length
    ? ((await check<Slot[]>(supabase.from("todo_slot").select(SLOT_COLS).in("todo_id", todos.map((t) => t.id)))) ?? []).map(asSlot)
    : [];
  return { todos, slots };
}

/** Every to-do from one Outlook series (by UID), with its sittings. */
export async function seriesTodos(uid: string): Promise<{ todos: Todo[]; slots: Slot[] }> {
  const todos = ((await check<Todo[]>(
    supabase.from("todo").select(TODO_COLS).eq("source", "outlook").eq("source_uid", uid),
  )) ?? []).map(asTodo);
  const slots = todos.length
    ? ((await check<Slot[]>(supabase.from("todo_slot").select(SLOT_COLS).in("todo_id", todos.map((t) => t.id)))) ?? []).map(asSlot)
    : [];
  return { todos, slots };
}

/**
 * Mark an Outlook event irrelevant: this occurrence, or (all) the whole
 * series. It is removed (logged occurrences stay, as they happened) and later
 * syncs skip it. (The app's undo puts it all back.)
 */
export async function dismissOutlook(t: Todo, slot: Slot | null, all: boolean): Promise<void> {
  const uid = t.source_uid ?? t.source_key ?? "";
  await addIgnore(uid, all ? null : t.source_key, t.title);
  const gone = all ? await seriesTodos(uid) : { todos: [t], slots: slot ? [slot] : [] };
  const removable = gone.todos.filter((x) => !gone.slots.some((s) => s.todo_id === x.id && s.entry_id));
  for (const x of removable) await deleteTodo(x.id);
}

const hhmm = (t: string | null) => (t ? t.slice(0, 5) : "");
function hours(m: Meeting): number | null {
  if (m.allDay) return null;
  const [sh, sm] = m.start.split(":").map(Number);
  const [eh, em] = m.end.split(":").map(Number);
  return Math.round(((eh * 60 + em - sh * 60 - sm) / 60) * 100) / 100;
}

async function fetchCalendar(): Promise<string> {
  const { data, error } = await supabase.functions.invoke(CALENDAR_FUNCTION, { method: "POST" });
  if (error) {
    let message = error.message;
    try {
      const body = await (error as { context?: Response }).context?.json();
      if (body?.error) message = body.error;
    } catch { /* keep the generic message */ }
    throw new Error(message);
  }
  if (typeof data !== "string") throw new Error("The calendar function returned something unexpected.");
  return data;
}

export async function syncOutlook(): Promise<SyncResult> {
  const { from, to } = syncWindow((await loadFeed())?.sync_weeks ?? 1);
  let text: string;
  try {
    text = await fetchCalendar();
  } catch (e) {
    await saveFeedStatus(`Failed: ${(e as Error).message}`).catch(() => {});
    throw e;
  }
  const events = meetingsInRange(text, from, to, { allDay: true });
  const uidsInCalendar = eventUids(text);

  const ignores = await loadIgnores();
  const ignored = (m: Meeting) =>
    ignores.some((i) => i.uid === m.uid && (i.occurrence === null || i.occurrence === m.key));

  const existing = ((await check<Todo[]>(
    supabase.from("todo").select(TODO_COLS).eq("source", "outlook").gte("due_on", from).lte("due_on", to),
  )) ?? []).map(asTodo);
  const slots = existing.length
    ? ((await check<Slot[]>(supabase.from("todo_slot").select(SLOT_COLS).in("todo_id", existing.map((t) => t.id)))) ?? []).map(asSlot)
    : [];
  const slotOf = (t: Todo) => slots.find((s) => s.todo_id === t.id) ?? null;
  const byKey = new Map(existing.map((t) => [t.source_key, t]));

  const result: SyncResult = { added: 0, updated: 0, removed: 0, skipped: 0, cleared: 0 };
  const seen = new Set<string>();

  for (const m of events) {
    if (ignored(m)) { result.skipped += 1; continue; }
    seen.add(m.key);
    const len = hours(m);
    const t = byKey.get(m.key);
    const outlookFields = {
      source_uid: m.uid, source_date: m.date, source_start: m.start || null, source_end: m.end || null,
      source_free: m.free, source_all_day: m.allDay, source_tentative: m.tentative,
    };

    if (!t) {
      const id = await saveTodo(null, {
        kind: m.allDay ? "task" : "meeting", title: m.title, due_on: m.date, est_hours: len,
        must_this_week: false, note: m.location || null,
        source: "outlook", source_key: m.key, reviewed: false, is_tentative: m.tentative, ...outlookFields,
      });
      await saveSlot(null, {
        todo_id: id, planned_on: m.date, start_time: m.start || null, end_time: m.end || null, planned_hours: len,
      });
      result.added += 1;
      continue;
    }

    const moved = t.source_date !== m.date || hhmm(t.source_start) !== m.start || hhmm(t.source_end) !== m.end;
    const renamed = !t.reviewed && t.title !== m.title;
    const s = slotOf(t);
    // back in Outlook after the sync struck it through; one you cancelled stays so
    const reappeared = !!s?.is_cancelled && s.cancelled_by_sync && !s.entry_id;
    // accepted or declined in Outlook since: the tentative mark follows (unless logged)
    const statusChanged = t.source_tentative !== m.tentative;
    if (!moved && !renamed && !reappeared && !statusChanged && t.source_free === m.free) continue;

    await saveTodo(t.id, {
      ...outlookFields,
      ...(renamed ? { title: m.title } : {}),
      ...(statusChanged && !s?.entry_id ? { is_tentative: m.tentative } : {}),
      ...(moved && !s?.entry_id ? { due_on: m.date, ...(m.allDay ? {} : { est_hours: len }) } : {}),
    });
    if (s && !s.entry_id && (moved || reappeared)) {
      await saveSlot(s.id, {
        planned_on: m.date, ...(reappeared ? { is_cancelled: false, cancelled_by_sync: false } : {}),
        ...(m.allDay ? {} : { start_time: m.start, end_time: m.end, planned_hours: len }),
      });
    }
    result.updated += 1;
  }

  // gone from Outlook (or cancelled there)
  for (const t of existing) {
    if (!t.source_key || seen.has(t.source_key)) continue;
    // a one-off event that still exists but now falls outside the window was moved, not removed
    if (!t.source_key.includes("|") && t.source_uid && uidsInCalendar.has(t.source_uid)) continue;
    const s = slotOf(t);
    if (s?.entry_id) continue; // logged: it happened
    if (!t.reviewed) {
      await deleteTodo(t.id);
      result.removed += 1;
    } else if (s && !s.is_cancelled) {
      await saveSlot(s.id, { is_cancelled: true, cancelled_by_sync: true });
      result.removed += 1;
    }
  }

  // keep the review list to the range: unreviewed events outside it go (they
  // come back if the range widens); kept ones stay whatever their date
  const outside = ((await check<Todo[]>(
    supabase.from("todo").select(TODO_COLS).eq("source", "outlook").eq("reviewed", false)
      .or(`due_on.lt.${from},due_on.gt.${to}`),
  )) ?? []).map(asTodo);
  if (outside.length) {
    const logged = new Set(((await check<Slot[]>(
      supabase.from("todo_slot").select(SLOT_COLS).in("todo_id", outside.map((t) => t.id)).not("entry_id", "is", null),
    )) ?? []).map((x) => x.todo_id));
    for (const t of outside.filter((x) => !logged.has(x.id))) {
      await deleteTodo(t.id);
      result.cleared += 1;
    }
  }

  const parts = [
    result.added && `${result.added} new`,
    result.updated && `${result.updated} changed`,
    result.removed && `${result.removed} removed`,
    result.cleared && `${result.cleared} outside the range cleared`,
  ].filter(Boolean);
  await saveFeedStatus(parts.length ? parts.join(", ") : "No changes");
  return result;
}

/** Due for a sync: a link is saved and the last sync is older than STALE_HOURS. */
export function isStale(feed: Feed | null): boolean {
  if (!feed?.ics_url) return false;
  if (!feed.last_synced_at) return true;
  return Date.now() - Date.parse(feed.last_synced_at) > STALE_HOURS * 3_600_000;
}
