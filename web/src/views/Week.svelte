<script lang="ts">
  import {
    loadTaxonomy, loadProjects, loadWeekPlan, loadUnfinishedBefore, loadEntriesBetween, loggedHoursOf, saveSlot, deleteSlot, saveTodo, deleteTodo, fmtHours,
    saveEntry, deleteEntry, loadAllHours, targetOn, loadIdeas, openSlotOn, loadIdeaNotes, addIdeaNote, saveIdeaNote, deleteIdeaNote,
  } from "../lib/data";
  import type { Taxonomy, Project, Milestone, Todo, Slot, TimeEntry, TimeEntryFields, IdeaNote } from "../lib/data";
  import { milestoneWeek } from "../lib/plan";
  import { shareRemaining } from "../lib/share";
  import type { MilestoneWeek } from "../lib/plan";
  import { addDays, today, weekStart, parse, fmtDay } from "../lib/dates";
  import { meetingsInRange } from "../lib/ics";
  import type { Meeting } from "../lib/ics";
  import EntryForm from "../lib/EntryForm.svelte";
  import TodoForm from "../lib/TodoForm.svelte";
  import CvForm from "../lib/CvForm.svelte";
  import OutlookInbox from "../lib/OutlookInbox.svelte";
  import OutlookSettings from "../lib/OutlookSettings.svelte";
  import { loadFeed, syncOutlook, isStale, loadUnreviewed, dismissOutlook } from "../lib/outlook";
  import type { Feed } from "../lib/outlook";
  import { undoable, nameLast, undoLast, quietly } from "../lib/undo.svelte";

  const SHOW_LOGGED = "week.showLogged";
  const LAST_CATEGORY = "log.category";

  // ---- week ------------------------------------------------------------------
  let offset = $state(0);
  const start = $derived(addDays(weekStart(today()), 7 * offset));
  const end = $derived(addDays(start, 6));
  const days = $derived(Array.from({ length: 7 }, (_, i) => addDays(start, i)));
  const isCurrent = $derived(offset === 0);

  // ---- data --------------------------------------------------------------------
  let tax = $state<Taxonomy | null>(null);
  let projects = $state<Project[]>([]);
  let todos = $state<Todo[]>([]);
  let slots = $state<Slot[]>([]);
  let entries = $state<TimeEntry[]>([]);
  let loading = $state(true);
  let error = $state("");
  let request = 0;

  loadTaxonomy().then((t) => (tax = t)).catch((e) => (error = e.message));

  // ---- Outlook: synced when Week opens (if stale) and on demand -------------------------
  let inbox = $state<{ todos: Todo[]; slots: Slot[] }>({ todos: [], slots: [] });
  let feed = $state<Feed | null>(null);
  let syncing = $state(false);
  let syncNote = $state("");

  async function runSync() {
    if (syncing) return;
    syncing = true;
    syncNote = "";
    try {
      const r = await quietly(syncOutlook); // not something to undo
      const parts = [r.added && `${r.added} new`, r.updated && `${r.updated} changed`, r.removed && `${r.removed} removed`,
                     r.cleared && `${r.cleared} outside the range cleared`].filter(Boolean);
      syncNote = parts.length ? parts.join(", ") : "up to date";
    } catch (e) {
      syncNote = `sync failed — ${(e as Error).message}`;
    }
    feed = await loadFeed().catch(() => feed);
    syncing = false;
    await load();
  }
  loadFeed()
    .then((f) => {
      feed = f;
      if (isStale(f)) runSync();
    })
    .catch(() => {}); // before 0005_outlook_sync.sql is run there is no feed table: Outlook stays off

  /** An Outlook event not yet kept: shown, but not counted as planned. */
  const pending = (t: Todo | undefined) => !!t && t.source === "outlook" && !t.reviewed;
  /** Kept as tentative: on the calendar, not counted as planned until confirmed. */
  const tentative = (t: Todo | undefined) => !!t && t.is_tentative && !pending(t);
  const uncounted = (t: Todo | undefined) => pending(t) || tentative(t);
  function syncedAt(f: Feed | null): string {
    if (!f?.last_synced_at) return "never synced";
    const d = new Date(f.last_synced_at);
    const sameDay = d.toDateString() === new Date().toDateString();
    return `synced ${sameDay ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`;
  }

  async function load() {
    const id = ++request;
    const [from, to] = [start, end];
    loading = true;
    try {
      const [plan, logged, p, review, thoughts, thoughtNotes] = await Promise.all([
        loadWeekPlan(from, to), loadEntriesBetween(from, to), loadProjects(), loadUnreviewed(), loadIdeas(), loadIdeaNotes(),
      ]);
      if (id !== request) return;
      projects = p;
      inbox = review;
      ideas = thoughts;
      ideaNotes = thoughtNotes;
      todos = plan.todos;
      slots = plan.slots;
      entries = logged;
      error = "";
    } catch (e) {
      if (id === request) error = (e as Error).message;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    void start;
    load();
  });

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
      await load();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  // ---- undo ----------------------------------------------------------------------
  // Changes here go into the app-wide undo (the header's ↶ Undo, Ctrl+Z) under
  // a name; the bar at the bottom names the latest one and offers to undo it.
  let toast = $state<{ text: string; canUndo: boolean } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | undefined;

  function showToast(text: string, canUndo: boolean) {
    toast = { text, canUndo };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 8000);
  }
  /** Name the change just made (its writes are already recorded for undo). */
  function remember(label: string) {
    nameLast(label);
    showToast(label, true);
  }
  /** Run a change as one undoable action. */
  /** Run a change, then reload; false if it failed (its error stays shown: the reload must not clear it). */
  async function change(label: string, run: () => Promise<unknown>): Promise<boolean> {
    let failed = "";
    try {
      await undoable(label, run);
      showToast(label, true);
    } catch (e) {
      failed = (e as Error).message;
    }
    await load();
    if (failed) error = failed;
    return !failed;
  }
  const q = (t: { title: string }) => `“${t.title}”`;

  // ---- lookups -------------------------------------------------------------------
  const todoById = $derived(new Map(todos.map((t) => [t.id, t])));
  const catById = $derived(new Map((tax?.allCategories ?? []).map((c) => [c.id, c])));
  const isActiveCategory = (id: string) => !!tax?.categories.some((c) => c.id === id);
  const projById = $derived(new Map(projects.map((p) => [p.id, p])));
  const entryById = $derived(new Map(entries.map((e) => [e.id, e])));

  function label(x: { category_id: string | null; project_id: string | null }): string {
    if (x.project_id) return projById.get(x.project_id)?.name ?? "";
    return x.category_id ? catById.get(x.category_id)?.label ?? "" : "";
  }

  const weekSlots = $derived(
    slots.filter((s) => s.planned_on >= start && s.planned_on <= end && !todoById.get(s.todo_id)?.is_cancelled),
  );
  function slotsOn(day: string, kind: "task" | "meeting"): Slot[] {
    return weekSlots
      .filter((s) => s.planned_on === day && todoById.get(s.todo_id)?.kind === kind)
      .sort((a, b) =>
        (a.start_time ?? "").localeCompare(b.start_time ?? "") || (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id.localeCompare(b.id));
  }
  function entriesOn(day: string): TimeEntry[] {
    return entries.filter((e) => e.started_at.slice(0, 10) === day);
  }
  const loggedOn = (day: string) => entriesOn(day).reduce((s, e) => s + e.minutes / 60, 0);

  // The week at a glance: planned (the days' figures added up, plus must-dos not
  // on the calendar yet), the flexible to-dos waiting, logged, and the weekly
  // target (every area's time plus email, as set in Planning).
  const weekTotals = $derived.by(() => {
    let calendar = 0, unknown = 0;
    for (const d of days) {
      const p = plannedOn(d);
      calendar += p.hours;
      unknown += p.unknown;
    }
    const must = listHours("must");
    const flex = listHours("flex");
    const planned = calendar + must.hours;
    unknown += must.unknown;
    const logged = entries.reduce((sum, e) => sum + e.minutes / 60, 0);
    const target = (tax?.areas ?? []).reduce((sum, a) => {
      const t = targetOn(tax!.targets, a.id, start);
      return sum + (t ? t.weekly_hours + t.email_weekly_hours : 0);
    }, 0);
    return { planned, calendar, must, flex, unknown, logged, target };
  });

  /** Hours still to do on the to-dos in a list (estimate less what is logged), and how many have no estimate. */
  function listHours(key: "must" | "flex") {
    const rows = (groups.find((g) => g.key === key)?.rows ?? []).filter((t) => !t.is_done && !t.is_cancelled);
    let hours = 0, unknown = 0;
    for (const t of rows) {
      if (t.est_hours === null || t.est_hours === undefined) unknown += 1;
      else hours += Math.max(0, t.est_hours - loggedFor(t));
    }
    return { hours, unknown, count: rows.length };
  }

  /** Hours planned on a day: meetings' lengths and duties' hours for that day, leaving
   *  out cancelled cards, finished (done) ones, and anything not yet counted (to
   *  review, or tentative). */
  function plannedOn(day: string): { hours: number; unknown: number } {
    let hours = 0, unknown = 0;
    for (const s of weekSlots) {
      if (s.planned_on !== day || s.is_cancelled) continue;
      const t = todoById.get(s.todo_id);
      if (!t || uncounted(t) || t.is_done) continue;
      const h = t.kind === "meeting" ? s.planned_hours : cardHours(s, t);
      // 0 is known (a missed day whose hours moved on); only no figure at all is unknown
      if (h === null || h === undefined) unknown += 1;
      else hours += h;
    }
    return { hours, unknown };
  }

  // ---- the week's to-do list ------------------------------------------------------
  const tasks = $derived(todos.filter((t) => t.kind === "task"));
  const live = $derived(tasks.filter((t) => !t.is_cancelled));
  // A to-do on a day this week shows on the calendar only; the list holds the
  // ones not placed yet. Cancelling its last day puts it back on the list.
  const onCalendar = $derived(new Set(weekSlots.filter((s) => !s.is_cancelled).map((s) => s.todo_id)));
  // Cancelled to-dos stay in their group, struck through, until restored or deleted.
  const unplaced = $derived(tasks.filter((t) => !onCalendar.has(t.id) && !pending(t)));
  const groups = $derived([
    { key: "must", title: "Must do", rows: unplaced.filter((t) => (!t.is_done || t.is_cancelled) && t.must_this_week) },
    { key: "flex", title: "Flexible", rows: unplaced.filter((t) => (!t.is_done || t.is_cancelled) && !t.must_this_week) },
    { key: "done", title: "Done", rows: unplaced.filter((t) => t.is_done && !t.is_cancelled) },
  ].map((g) => ({ ...g, rows: [...g.rows].sort((a, b) => a.sort_order - b.sort_order || a.title.localeCompare(b.title)) })));

  function slotsOf(t: Todo): Slot[] {
    return slots.filter((s) => s.todo_id === t.id).sort((a, b) => a.planned_on.localeCompare(b.planned_on));
  }
  function loggedFor(t: Todo): number {
    return slotsOf(t).reduce((s, x) => s + ((x.entry_id && entryById.get(x.entry_id)?.minutes) || 0) / 60, 0);
  }

  // ---- summary ----------------------------------------------------------------------
  const summary = $derived.by(() => {
    const meetingH = weekSlots
      .filter((s) => todoById.get(s.todo_id)?.kind === "meeting" && !s.is_cancelled && !uncounted(todoById.get(s.todo_id)))
      .reduce((s, x) => s + (x.planned_hours ?? 0), 0);
    const open = live.filter((t) => !t.is_done && !uncounted(t));
    const dutyH = open.reduce((s, t) => s + (t.est_hours ?? 0), 0);
    const must = live.filter((t) => t.must_this_week && !uncounted(t));
    const tentativeH = weekSlots
      .filter((s) => !s.is_cancelled && tentative(todoById.get(s.todo_id)))
      .reduce((sum, x) => sum + (x.planned_hours ?? todoById.get(x.todo_id)?.est_hours ?? 0), 0);
    const logged = entries.reduce((s, e) => s + e.minutes / 60, 0);
    return { meetingH, dutyH, logged, tentativeH, mustDone: must.filter((t) => t.is_done).length, mustAll: must.length };
  });

  // ---- actions ------------------------------------------------------------------------
  /** The to-do's open (not logged, not cancelled) card on a day, other than `except`. */
  function openCardOn(todoId: string, day: string, except?: string): Slot | undefined {
    return slots.find((x) => x.todo_id === todoId && x.planned_on === day && x.id !== except && !x.entry_id && !x.is_cancelled);
  }
  const sumHours = (a: number | null, b: number | null) => (a === null && b === null ? null : (a ?? 0) + (b ?? 0));

  function placeOn(t: Todo, day: string) {
    if (openCardOn(t.id, day)) {
      showToast(`${q(t)} is already on ${dayName(day)} ${dayNum(day)}`, false);
      return;
    }
    return change(`Planned ${q(t)} on ${dayName(day)} ${dayNum(day)}`,
      () => saveSlot(null, { todo_id: t.id, planned_on: day, planned_hours: null }));
  }

  /** A second (third…) card for the same to-do on the same day: separate sessions, each logged on its own. */
  function addSession(t: Todo, day: string) {
    return change(`Added another session of ${q(t)} on ${dayName(day)} ${dayNum(day)}`,
      () => saveSlot(null, { todo_id: t.id, planned_on: day, planned_hours: null }));
  }

  // Moving a card onto a day that already holds the same to-do merges the two
  // into one card with their hours added.
  const move = (s: Slot, by: number) => moveTo(s, addDays(s.planned_on, by));
  /** A card to any day, in this week or another. A to-do with no other open card
   *  goes along to that day's week (as carrying forward does); one already on that
   *  day takes the card's hours. */
  async function moveTo(s: Slot, to: string) {
    const t = todoById.get(s.todo_id)!;
    if (to === s.planned_on) return;
    const shown = to >= start && to <= end;
    const where = shown ? `${dayName(to)} ${dayNum(to)}` : fmtDay(to);
    let there: Slot | null | undefined;
    try {
      there = shown ? openCardOn(t.id, to, s.id) : await openSlotOn(t.id, to, s.id);
    } catch (e) {
      error = (e as Error).message;
      return;
    }
    const week = weekStart(to);
    const refile = week !== weekStart(t.due_on) && !slotsOf(t).some((x) => x.id !== s.id && !x.entry_id && !x.is_cancelled);
    const filed = refile ? ` — now in the week of ${fmtDay(week)}` : "";
    const merged = there ? sumHours(there.planned_hours, s.planned_hours) : null;
    return change(there
      ? `Merged ${q(t)} into ${where}${merged ? ` (${fmtHours(merged)})` : ""}${filed}`
      : `Moved ${q(t)} to ${where}${filed}`,
      async () => {
        if (there) {
          await saveSlot(there.id, { planned_hours: merged });
          await deleteSlot(s.id);
        } else {
          await saveSlot(s.id, { planned_on: to });
        }
        if (refile) await saveTodo(t.id, { due_on: week });
      });
  }
  let moveDate = $state("");
  function openMoveTo(t: Todo, s: Slot) {
    moveDate = s.planned_on;
    panel = { kind: "moveTo", todo: t, slot: s };
  }

  /** Hours of a logged card's to-do with no day left to go to: what is left of the
   *  estimate (or of this card's plan, without one), when positive. While the to-do
   *  has an open day, that day already holds the rest, so there is nothing to move. */
  function remainingOf(s: Slot, t: Todo): number {
    const e = s.entry_id ? entryById.get(s.entry_id) : null;
    if (!e) return 0;
    if (slotsOf(t).some((x) => !x.entry_id && !x.is_cancelled)) return 0;
    const planned = cardHours(s, t);
    const raw = t.est_hours !== null ? t.est_hours - loggedFor(t) : planned === null ? 0 : planned - e.minutes / 60;
    const left = Math.round(raw * 4) / 4;
    return left > 0 ? left : 0;
  }
  /** A partly done day: it keeps what was logged; the rest joins (or makes) the next day's card. */
  function moveRest(s: Slot, by: number) {
    const t = todoById.get(s.todo_id)!;
    const rest = remainingOf(s, t);
    if (!rest) return;
    const to = addDays(s.planned_on, by);
    const there = openCardOn(t.id, to, s.id);
    const e = entryById.get(s.entry_id!);
    const done = e ? e.minutes / 60 : (cardHours(s, t) ?? 0) - rest;
    return change(`Moved the remaining ${fmtHours(rest)} of ${q(t)} to ${dayName(to)} ${dayNum(to)}`,
      async () => {
        await saveSlot(s.id, { planned_hours: done });
        if (there) await saveSlot(there.id, { planned_hours: sumHours(there.planned_hours, rest) });
        else await saveSlot(null, { todo_id: t.id, planned_on: to, planned_hours: rest });
      });
  }
  function unplan(s: Slot) {
    const t = todoById.get(s.todo_id);
    if (!t) return;
    if (t.kind === "meeting") {
      if (!confirm(`Delete the meeting “${t.title}”?${s.entry_id ? " Its logged time stays." : ""} (Use Edit to change its time.)`)) return;
      return change(`Deleted the meeting ${q(t)}`, () => deleteTodo(t.id));
    }
    if (s.entry_id && !confirm("This day was logged. Remove it from the plan? The logged time stays.")) return;
    return change(`Took ${q(t)} off ${dayName(s.planned_on)} ${dayNum(s.planned_on)}`, () => deleteSlot(s.id));
  }
  // Cancelling keeps the card on its day, struck through, so the week still
  // shows what was planned; it can be restored. ✕ takes it off altogether.
  function setCancelled(s: Slot, cancelled: boolean) {
    const t = todoById.get(s.todo_id)!;
    return change(`${cancelled ? "Cancelled" : "Restored"} ${q(t)} on ${dayName(s.planned_on)} ${dayNum(s.planned_on)}`,
      () => saveSlot(s.id, { is_cancelled: cancelled, cancelled_by_sync: false })); // yours: the Outlook sync leaves it be
  }
  function setDone(t: Todo, done: boolean) {
    return change(done ? `Marked ${q(t)} done` : `Reopened ${q(t)}`,
      () => saveTodo(t.id, { is_done: done, done_at: done ? new Date().toISOString() : null }));
  }
  function setMust(t: Todo) {
    const was = t.must_this_week;
    return change(`Made ${q(t)} ${was ? "flexible" : "a must-do"}`,
      () => saveTodo(t.id, { must_this_week: !was }));
  }
  function setTentative(t: Todo, on: boolean, keep = false) {
    return change(on ? `Marked ${q(t)} tentative` : `Confirmed ${q(t)}`,
      () => saveTodo(t.id, { is_tentative: on, ...(keep ? { reviewed: true } : {}) }));
  }
  function keepAsIs(t: Todo) {
    return change(`Kept ${q(t)}`, () => saveTodo(t.id, { reviewed: true }));
  }
  function ignoreEvent(t: Todo, s: Slot | null, all: boolean) {
    return change(all ? `Ignored ${q(t)} and its repeats` : `Ignored ${q(t)}`, () => dismissOutlook(t, s, all));
  }
  function cancelTodo(t: Todo) {
    return change(`Cancelled ${q(t)}`,
      () => saveTodo(t.id, { is_cancelled: true }));
  }
  function deleteWhole(t: Todo) {
    const logged = slotsOf(t).some((x) => x.entry_id);
    if (!confirm(`Delete “${t.title}”${slotsOf(t).length ? " and its planned days" : ""}?${logged ? " Logged time stays." : ""}`)) return;
    return change(`Deleted ${q(t)}`, () => deleteTodo(t.id));
  }
  function restore(t: Todo) {
    return change(`Restored ${q(t)}`,
      () => saveTodo(t.id, { is_cancelled: false }));
  }

  // ---- card menu: click or right-click a card ------------------------------------------
  // The cards stay quiet (title, tick, status); their actions live in one menu.
  type Menu = { slot: Slot; day: string; x: number; y: number };
  type Item = { label: string; run: () => unknown; danger?: boolean };
  let menu = $state<Menu | null>(null);
  const MENU_W = 220;
  const MENU_H = 290;

  function openMenu(ev: MouseEvent, slot: Slot, day: string) {
    ev.preventDefault();
    ev.stopPropagation();
    let x: number;
    let y: number;
    if (ev.type === "contextmenu") {
      x = ev.clientX;
      y = ev.clientY;
    } else {
      const r = (ev.currentTarget as HTMLElement).getBoundingClientRect();
      x = r.left;
      y = r.bottom + 2;
    }
    menu = {
      slot,
      day,
      x: Math.max(8, Math.min(x, window.innerWidth - MENU_W - 8)),
      y: Math.max(8, Math.min(y, window.innerHeight - MENU_H - 8)),
    };
  }
  const closeMenu = () => (menu = null);

  function menuItems(m: Menu): Item[] {
    const s = m.slot;
    const t = todoById.get(s.todo_id);
    if (!t) return [];
    const meeting = t.kind === "meeting";
    const fromOutlook: Item[] = t.source === "outlook"
      ? [
          ...(pending(t) ? [{ label: "✓ Keep as it is", run: () => keepAsIs(t) }] : []),
          { label: pending(t) ? "Irrelevant" : "Irrelevant — stop syncing it", run: () => ignoreEvent(t, s, false), danger: true },
          ...(t.source_key?.includes("|")
            ? [{ label: "Irrelevant — all repeats", run: () => ignoreEvent(t, s, true), danger: true }]
            : []),
        ]
      : [];
    if (pending(t)) {
      return [
        ...fromOutlook.slice(0, 1),
        { label: "Keep as tentative", run: () => setTentative(t, true, true) },
        ...fromOutlook.slice(1),
        { label: "Edit…", run: () => (panel = { kind: "todo", todo: t }) },
      ];
    }
    const tentativeItem: Item = t.is_tentative
      ? { label: "✓ Confirm (no longer tentative)", run: () => setTentative(t, false) }
      : { label: "Mark tentative", run: () => setTentative(t, true) };
    const edit: Item = { label: meeting ? "Edit meeting" : "Edit to-do", run: () => (panel = { kind: "todo", todo: t }) };
    const remove: Item = meeting
      ? { label: "Delete meeting", run: () => unplan(s), danger: true }
      : { label: "Take off the calendar", run: () => unplan(s), danger: true };
    const done: Item[] = meeting
      ? []
      : [t.is_done
          ? { label: "Reopen to-do", run: () => setDone(t, false) }
          : { label: "✔ Mark to-do done", run: () => setDone(t, true) }];
    if (s.is_cancelled) return [{ label: "Restore", run: () => setCancelled(s, false) }, edit, remove, ...fromOutlook];
    if (s.entry_id) {
      const e = entryById.get(s.entry_id);
      const rest = meeting ? 0 : remainingOf(s, t);
      const restItems: Item[] = rest
        ? [{ label: `Move the remaining ${fmtHours(rest)} to the day after ›`, run: () => moveRest(s, 1) }]
        : [];
      const another: Item[] = meeting ? [] : [{ label: "+ Another session on this day", run: () => addSession(t, m.day) }];
      return [...done, ...another, ...restItems, ...(e ? [{ label: "Open logged entry", run: () => openEntry(e, m.day) }] : []), edit, remove];
    }
    const moves: Item[] = meeting
      ? []
      : [
          { label: "‹ Move to the day before", run: () => move(s, -1) },
          { label: "Move to the day after ›", run: () => move(s, 1) },
          { label: "Move to a date…", run: () => openMoveTo(t, s) },
        ];
    return [
      ...(t.is_tentative ? [tentativeItem] : []),
      { label: "✓ Log time", run: () => openLog(t, s, m.day) },
      ...(t.is_tentative ? [] : [tentativeItem]),
      ...(meeting ? [] : [{ label: "+ Another session on this day", run: () => addSession(t, m.day) }]),
      ...(meeting ? [] : [{ label: "Plan across days…", run: () => openSpread(t) }]),
      ...done,
      ...moves,
      { label: meeting ? "Cancel meeting (keep, struck through)" : "Cancel this day (keep, struck through)", run: () => setCancelled(s, true) },
      ...(meeting ? [] : [{ label: "Cancel the whole to-do (keep, struck through)", run: () => cancelTodo(t) }]),
      edit,
      remove,
      ...(meeting ? [] : [{ label: "Delete the to-do", run: () => deleteWhole(t), danger: true }]),
      ...fromOutlook,
    ];
  }

  // (Ctrl/Cmd+Z is the app's, for every tab.)
  function keys(ev: KeyboardEvent) {
    if (menu) return menuKeys(ev);
  }

  function focusFirst(node: HTMLElement) {
    (node.querySelector("button") as HTMLButtonElement | null)?.focus();
  }
  function menuKeys(ev: KeyboardEvent) {
    if (!menu) return;
    if (ev.key === "Escape") return closeMenu();
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    ev.preventDefault();
    const items = [...document.querySelectorAll<HTMLButtonElement>(".menu button")];
    const i = items.indexOf(document.activeElement as HTMLButtonElement);
    items[(i + (ev.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
  }

  // ---- dialogs: edit/add a to-do, log a sitting ----------------------------------------
  type Panel =
    | { kind: "todo"; todo: Todo | null; day?: string; as?: "task" | "meeting"; place?: boolean }
    | { kind: "log"; todo: Todo; slot: Slot | null; day: string }
    | { kind: "entry"; entry: TimeEntry | null; day: string }
    | { kind: "spread"; todo: Todo }
    | { kind: "moveTo"; todo: Todo; slot: Slot }
    | { kind: "email" }
    | { kind: "forward" }
    | { kind: "outlook" }
    | { kind: "milestones" };
  let panel = $state<Panel | null>(null);
  let markDone = $state(false);
  let cvOpen = $state(false); // the CV form inside an entry's dialog
  let dialog = $state<HTMLDialogElement | null>(null);

  $effect(() => {
    if (!dialog) return;
    if (panel && !dialog.open) dialog.showModal();
    if (!panel && dialog.open) dialog.close();
  });

  function openEntry(entry: TimeEntry | null, day: string) {
    cvOpen = false;
    panel = { kind: "entry", entry, day };
  }

  function openLog(t: Todo, slot: Slot | null, day: string) {
    // a logged meeting has happened; a to-do may need more, so you tick it done yourself
    markDone = t.kind === "meeting";
    panel = { kind: "log", todo: t, slot, day };
  }

  function lastCategory(): string {
    try { return localStorage.getItem(LAST_CATEGORY) ?? ""; } catch { return ""; }
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  function plusHours(hhmm: string, h: number): string {
    const [a, b] = hhmm.split(":").map(Number);
    const m = Math.min(a * 60 + b + Math.round(h * 60), 24 * 60);
    return m >= 24 * 60 ? "00:00" : `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  }
  function logDefaults(p: Extract<Panel, { kind: "log" }>) {
    const t = p.todo;
    const saved = lastCategory();
    const categoryId = t.category_id ?? (isActiveCategory(saved) ? saved : tax?.categories[0]?.id ?? "");
    let s = p.slot?.start_time?.slice(0, 5);
    let e = p.slot?.end_time?.slice(0, 5);
    if (!s) {
      const ends = entriesOn(p.day).map((x) => x.ended_at?.slice(11, 16)).filter((x): x is string => !!x).sort();
      s = ends.length ? ends[ends.length - 1] : "09:00";
      e = plusHours(s, p.slot?.planned_hours ?? t.est_hours ?? 1);
    }
    return {
      date: p.day, start: s, end: e!, categoryId, projectId: t.project_id,
      milestoneId: t.milestone_id, description: t.title, isCore: t.is_core,
    };
  }

  // A plain log starts where that day's last entry ended (else 09:00) and, for
  // today, ends now rounded to the quarter hour when that is later.
  function entryDefaults(day: string) {
    const ends = entriesOn(day).map((x) => x.ended_at?.slice(11, 16)).filter((x): x is string => !!x).sort();
    const s = ends.length ? ends[ends.length - 1] : "09:00";
    let e = plusHours(s, 1);
    if (day === today()) {
      const now = new Date();
      const q = Math.round((now.getHours() * 60 + now.getMinutes()) / 15) * 15;
      const [sh, sm] = s.split(":").map(Number);
      if (q > sh * 60 + sm) e = q >= 24 * 60 ? "00:00" : `${pad(Math.floor(q / 60))}:${pad(q % 60)}`;
    }
    const saved = lastCategory();
    const categoryId = isActiveCategory(saved) ? saved : tax?.categories[0]?.id ?? "";
    return { date: day, start: s, end: e, categoryId };
  }

  async function entrySaved(p: Extract<Panel, { kind: "entry" }>, f: TimeEntryFields, id: string,
                            action: "created" | "updated" | "copied" | "deleted") {
    try { localStorage.setItem(LAST_CATEGORY, f.category_id); } catch {}
    const when = `${dayName(f.started_at.slice(0, 10))} ${dayNum(f.started_at.slice(0, 10))}`;
    if (action === "created") remember(`Logged ${label(f) || "time"} on ${when}`);
    else if (action === "copied") remember(`Copied the entry to ${when}`);
    else if (action === "deleted") remember(`Deleted the entry on ${when}`);
    else remember(`Changed the entry on ${when}`);
    panel = null;
    await load();
  }

  async function logged(p: Extract<Panel, { kind: "log" }>, f: TimeEntryFields, entryId: string) {
    const markedDone = markDone && !p.todo.is_done;
    try {
      // these join the entry just saved, as one action
      const day = f.started_at.slice(0, 10);
      if (p.slot) await saveSlot(p.slot.id, { entry_id: entryId, planned_on: day });
      else await saveSlot(null, { todo_id: p.todo.id, planned_on: day, entry_id: entryId });
      if (markedDone) await saveTodo(p.todo.id, { is_done: true, done_at: new Date().toISOString() });
      try { localStorage.setItem(LAST_CATEGORY, f.category_id); } catch {}
      remember(`Logged ${q(p.todo)}`);
    } catch (e) {
      error = (e as Error).message;
    }
    panel = null;
    await load();
  }

  async function closed(info: { action: "created" | "updated" | "deleted" | "cancelled" | "restored"; ids?: string[] }) {
    const p = panel;
    const t = p && p.kind === "todo" && p.todo ? p.todo : null;
    if (info.action === "created" && info.ids?.length) {
      remember(info.ids.length > 1 ? `Added ${info.ids.length} meetings` : "Added a to-do");
    } else if (t && info.action === "deleted") {
      remember(`Deleted ${q(t)}`);
    } else if (t && (info.action === "cancelled" || info.action === "restored")) {
      remember(`${info.action === "cancelled" ? "Cancelled" : "Restored"} ${q(t)}`);
    } else if (t && info.action === "updated") {
      remember(`Edited ${q(t)}`);
    }
    panel = null;
    await load();
  }

  // ---- plan a to-do across several days ------------------------------------------------
  // Tick the days and give the total; the hours are split evenly over them.
  // A day already logged stays ticked (its time is part of the total).
  let spreadPick = $state<Record<string, boolean>>({});
  let spreadHours = $state<number | null>(null);

  function openSpread(t: Todo) {
    const live = slotsOf(t).filter((x) => !x.is_cancelled && x.planned_on >= start && x.planned_on <= end);
    spreadPick = Object.fromEntries(days.map((d) => [d, live.some((x) => x.planned_on === d)]));
    const planned = live.reduce((sum, x) => sum + (x.planned_hours ?? 0), 0);
    spreadHours = t.est_hours ?? (planned || null);
    panel = { kind: "spread", todo: t };
  }
  const spreadDays = $derived(days.filter((d) => spreadPick[d]));
  const perDay = $derived(spreadHours && spreadDays.length ? Math.round((spreadHours / spreadDays.length) * 100) / 100 : null);

  async function saveSpread(t: Todo) {
    const before = slotsOf(t).filter((x) => x.planned_on >= start && x.planned_on <= end);
    const estBefore = t.est_hours;
    const label = `Planned ${q(t)} over ${spreadDays.length} ${spreadDays.length === 1 ? "day" : "days"}`;
    try {
      await undoable(label, async () => {
      for (const d of days) {
        const here = before.filter((x) => x.planned_on === d && !x.is_cancelled);
        if (spreadPick[d]) {
          if (here.length) {
            for (const x of here) await saveSlot(x.id, { planned_hours: perDay });
          } else {
            await saveSlot(null, { todo_id: t.id, planned_on: d, planned_hours: perDay });
          }
        } else {
          for (const x of here.filter((x) => !x.entry_id)) await deleteSlot(x.id);
        }
      }
      if (spreadHours !== estBefore) await saveTodo(t.id, { est_hours: spreadHours });
      });
      showToast(label, true);
    } catch (e) {
      error = (e as Error).message;
    }
    panel = null;
    await load();
  }

  // ---- "To think about": ideas jotted down as they come ------------------------------------
  // Not tied to a week and never counted as planned; listed until done, deleted,
  // or turned into a to-do for the week.
  let ideas = $state<Todo[]>([]);
  let ideaText = $state("");
  let ideaEditing = $state<string | null>(null);
  let ideaDraft = $state({ title: "", note: "" }); // note: an idea's one note from before 0044
  // each idea's notes, dated, added one at a time as the thought develops
  let ideaNotes = $state<IdeaNote[]>([]);
  const notesOf = (t: Todo) => ideaNotes.filter((n) => n.todo_id === t.id);
  let noteFor = $state<string | null>(null); // the idea being given a new note
  let noteEditing = $state<string | null>(null); // or the note being edited
  let noteText = $state("");
  let noteError = $state("");

  async function addIdea(event: SubmitEvent) {
    event.preventDefault();
    const title = ideaText.trim();
    if (!title) return;
    ideaText = "";
    const sort_order = Math.max(0, ...ideas.map((t) => t.sort_order)) + 10; // newest at the bottom
    await change(`Jotted down “${title}”`,
      () => saveTodo(null, { kind: "idea", title, due_on: today(), must_this_week: false, sort_order }));
  }

  // ---- rearranging ideas: drag the ⠿ handle (mouse or touch), or arrow keys on it ----
  let dragOrder = $state<string[] | null>(null); // ids, while dragging
  let dragId = $state<string | null>(null);
  const shownIdeas = $derived(
    dragOrder ? dragOrder.map((id) => ideas.find((t) => t.id === id)).filter((t): t is Todo => !!t) : ideas,
  );

  // The window follows the pointer for the whole drag: the dragged row moves in
  // the page as the order changes, which would drop a capture held by its handle.
  function startDrag(ev: PointerEvent, t: Todo) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    dragId = t.id;
    dragOrder = ideas.map((x) => x.id);
    window.addEventListener("pointermove", dragMove);
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
  }
  function dragMove(ev: PointerEvent) {
    if (!dragId || !dragOrder) return;
    const over = (document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null)?.closest<HTMLElement>("li.idea");
    const overId = over?.dataset.id;
    if (!overId || overId === dragId) return;
    const order = dragOrder.filter((id) => id !== dragId);
    const r = over!.getBoundingClientRect();
    const at = order.indexOf(overId) + (ev.clientY > r.top + r.height / 2 ? 1 : 0);
    order.splice(at, 0, dragId);
    if (order.join() !== dragOrder.join()) dragOrder = order;
  }
  async function endDrag() {
    window.removeEventListener("pointermove", dragMove);
    window.removeEventListener("pointerup", endDrag);
    window.removeEventListener("pointercancel", endDrag);
    if (!dragOrder) return;
    const order = dragOrder;
    dragOrder = null;
    dragId = null;
    await saveIdeaOrder(order);
  }
  function keyMove(ev: KeyboardEvent, t: Todo) {
    if (ev.key !== "ArrowUp" && ev.key !== "ArrowDown") return;
    ev.preventDefault();
    const order = ideas.map((x) => x.id);
    const i = order.indexOf(t.id);
    const j = i + (ev.key === "ArrowUp" ? -1 : 1);
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    saveIdeaOrder(order).then(() => {
      // keep the focus on the moved idea's handle
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`li.idea[data-id="${t.id}"] .grip`)?.focus());
    });
  }
  /** Store an order as sort_order 10, 20, 30…, changing only what moved. */
  async function saveIdeaOrder(order: string[]) {
    const before = new Map(ideas.map((t) => [t.id, t.sort_order]));
    const changes = order
      .map((id, i) => ({ id, sort_order: (i + 1) * 10 }))
      .filter((c) => before.get(c.id) !== c.sort_order);
    if (!changes.length) return;
    // show the new order at once; the reload confirms it
    ideas = order.map((id, i) => ({ ...ideas.find((t) => t.id === id)!, sort_order: (i + 1) * 10 }));
    await change("Reordered your ideas",
      async () => { for (const c of changes) await saveTodo(c.id, { sort_order: c.sort_order }); });
  }
  /** Text split around web addresses, so each address can show as a short "link". */
  function linkParts(text: string): { text?: string; url?: string }[] {
    const out: { text?: string; url?: string }[] = [];
    const re = /https?:\/\/[^\s<>"']+[^\s<>"'.,;:!?)\]]/g;
    let last = 0;
    for (const m of text.matchAll(re)) {
      let url = m[0];
      // keep a closing bracket the address itself opened, e.g. …/Thing_(topic)
      const opens = (url.match(/\(/g) ?? []).length;
      const closes = (url.match(/\)/g) ?? []).length;
      if (opens > closes && text[m.index! + url.length] === ")") url += ")";
      if (m.index! > last) out.push({ text: text.slice(last, m.index) });
      out.push({ url });
      last = m.index! + url.length;
    }
    if (last < text.length) out.push({ text: text.slice(last) });
    return out;
  }

  function editIdea(t: Todo) {
    ideaEditing = t.id;
    ideaError = "";
    ideaDraft = { title: t.title, note: t.note ?? "" };
  }
  // the editor stays open (with what you wrote) until the save has gone through
  let ideaError = $state("");
  async function saveIdea(t: Todo) {
    const title = ideaDraft.title.trim();
    if (!title) return;
    ideaError = "";
    if (await change(`Edited ${q(t)}`, () => saveTodo(t.id, { title, note: ideaDraft.note.trim() || null }))) ideaEditing = null;
    else ideaError = error;
  }
  // Ctrl+Enter (⌘+Enter) saves, Escape cancels
  function ideaKeys(ev: KeyboardEvent, t: Todo) {
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); saveIdea(t); }
    if (ev.key === "Escape") ideaEditing = null;
  }
  function startNote(t: Todo, n?: IdeaNote) {
    noteFor = n ? null : t.id;
    noteEditing = n?.id ?? null;
    noteText = n?.body ?? "";
    noteError = "";
  }
  const stopNote = () => { noteFor = noteEditing = null; };
  // the box stays open (with what you wrote) until the save has gone through
  async function saveNote(t: Todo) {
    const body = noteText.trim();
    if (!body) return;
    noteError = "";
    const editingId = noteEditing;
    const ok = editingId
      ? await change(`Edited a note on ${q(t)}`, () => saveIdeaNote(editingId, body))
      : await change(`Added a note to ${q(t)}`, () => addIdeaNote(t.id, body));
    if (ok) stopNote();
    else noteError = error;
  }
  // Ctrl+Enter (⌘+Enter) saves, Escape cancels
  function noteKeys(ev: KeyboardEvent, t: Todo) {
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); saveNote(t); }
    if (ev.key === "Escape") stopNote();
  }
  function deleteNote(t: Todo, n: IdeaNote) {
    if (!confirm("Delete this note?")) return;
    return change(`Deleted a note on ${q(t)}`, () => deleteIdeaNote(n.id));
  }
  function ideaDone(t: Todo) {
    return change(`Thought through ${q(t)}`,
      () => saveTodo(t.id, { is_done: true, done_at: new Date().toISOString() }));
  }
  function ideaToTodo(t: Todo) {
    const day = isCurrent ? today() : start;
    return change(`Turned ${q(t)} into a to-do`,
      () => saveTodo(t.id, { kind: "task", due_on: day }));
  }
  function deleteIdea(t: Todo) {
    if (!confirm(`Delete “${t.title}”?`)) return;
    return change(`Deleted ${q(t)}`, () => deleteTodo(t.id));
  }

  // ---- to-dos from milestones live this week ------------------------------------------------
  // Each milestone whose dates touch the week (or which is overdue) is offered
  // with this week's share of its remaining hours; ticked ones become to-dos
  // linked to the milestone, its project and category.
  // `existing`: an open to-do this week already linked to the milestone — noted, and
  // the row starts unticked, but it can still be added (e.g. a different task on it)
  type MsRow = { p: Project; m: Milestone; info: MilestoneWeek; existing: Todo | null; pick: boolean; hours: number | null; must: boolean };
  let msRows = $state<MsRow[]>([]);
  let msLoading = $state(false);
  // which sections are open: set once when the window opens (urgent ones),
  // then only by you — ticking a box must not fold its section
  let msOpen = $state<Record<string, boolean>>({});

  async function openMilestones() {
    panel = { kind: "milestones" };
    msLoading = true;
    msRows = [];
    try {
      const logged = new Map<string, number>();
      for (const h of await loadAllHours()) {
        if (h.milestone_id) logged.set(h.milestone_id, (logged.get(h.milestone_id) ?? 0) + h.hours);
      }
      const week = { from: start, to: end };
      const rows: MsRow[] = [];
      for (const p of projects) {
        for (const m of p.milestone) {
          const info = milestoneWeek(p, m, logged.get(m.id) ?? 0, week, today());
          if (!info) continue;
          const existing = todos.find((t) => t.milestone_id === m.id && t.kind === "task" && !t.is_cancelled && !t.is_done) ?? null;
          const urgent = info.overdue || info.dueThisWeek;
          rows.push({ p, m, info, existing, pick: !existing && urgent, hours: info.suggested, must: m.hard_deadline || urgent });
        }
      }
      // overdue first, then by due date; undated last
      msRows = rows.sort((a, b) =>
        Number(b.info.overdue) - Number(a.info.overdue) || (a.info.due ?? "9").localeCompare(b.info.due ?? "9"));
      msOpen = Object.fromEntries(msGroups.map((g) => [g.key, g.urgent]));
    } catch (e) {
      error = (e as Error).message;
    } finally {
      msLoading = false;
    }
  }

  type MsProject = { p: Project; rows: MsRow[] };
  type MsGroup = { key: string; label: string; urgent: boolean; projects: MsProject[] };
  const msGroups = $derived.by(() => {
    if (!tax) return [] as MsGroup[];
    const out: MsGroup[] = [];
    for (const a of tax.areas) {
      for (const c of tax.categories.filter((x) => x.area_id === a.id)) {
        const rows = msRows.filter((r) => r.p.category_id === c.id);
        if (!rows.length) continue;
        const byProject = new Map<string, MsProject>();
        for (const r of rows) {
          if (!byProject.has(r.p.id)) byProject.set(r.p.id, { p: r.p, rows: [] });
          byProject.get(r.p.id)!.rows.push(r);
        }
        out.push({
          key: c.id,
          label: `${a.label} › ${c.label}`,
          urgent: rows.some((r) => !r.existing && (r.info.overdue || r.info.dueThisWeek)),
          projects: [...byProject.values()].sort((x, y) => x.p.name.localeCompare(y.p.name)),
        });
      }
    }
    return out;
  });
  const pickedIn = (rows: MsRow[]) => rows.filter((r) => r.pick).length;
  function pickAll(rows: MsRow[], on: boolean) {
    for (const r of rows) r.pick = on;
  }

  async function addFromMilestones() {
    const picked = msRows.filter((r) => r.pick);
    if (picked.length) await change(`Added ${picked.length} to-${picked.length === 1 ? "do" : "dos"} from milestones`, async () => {
      for (const r of picked) {
        await saveTodo(null, {
          kind: "task", title: r.m.title, due_on: isCurrent ? today() : start,
          category_id: r.p.category_id, project_id: r.p.id, milestone_id: r.m.id,
          est_hours: r.hours, must_this_week: r.must,
        });
      }
    });
    panel = null;
  }

  // ---- carrying unfinished to-dos forward, by hand ------------------------------------------
  // Nothing comes along by itself: this lists the open to-dos filed before the
  // week they go into — the week on screen, or the one after it (so this week's
  // leftovers can be sent on) — none ticked, and files the ticked ones there. A
  // day planned for one before that week and never logged is cancelled (kept,
  // struck through), so it no longer holds hours that now belong to the new week.
  type FwdRow = { t: Todo; pick: boolean; week: string; loggedDays: number };
  let fwdRows = $state<FwdRow[]>([]);
  let fwdSlots = $state<Slot[]>([]);
  let fwdLoading = $state(false);
  let fwdTo = $state(""); // the week they go into: the one on screen, or the next
  const fwdWeeks = $derived([...new Set(fwdRows.map((r) => r.week))]);

  async function openForward(to: string = start) {
    panel = { kind: "forward" };
    fwdTo = to;
    fwdLoading = true;
    fwdRows = [];
    try {
      const plan = await loadUnfinishedBefore(to);
      if (fwdTo !== to) return; // the choice changed while this was loading
      fwdSlots = plan.slots;
      fwdRows = plan.todos.map((t) => ({
        t, pick: false, week: weekStart(t.due_on),
        loggedDays: plan.slots.filter((s) => s.todo_id === t.id && s.entry_id).length,
      }));
    } catch (e) {
      error = (e as Error).message;
    } finally {
      fwdLoading = false;
    }
  }
  async function forwardPicked() {
    const picked = fwdRows.filter((r) => r.pick).map((r) => r.t);
    if (!picked.length) return;
    panel = null;
    const n = picked.length;
    const to = fwdTo;
    // an email check folds into the one already in that week, if there is one
    const targetEmail = picked.some(isEmail)
      ? (await loadWeekPlan(to, addDays(to, 6)).catch(() => null))?.todos
          .find((x) => isEmail(x) && x.kind === "task" && !x.is_cancelled && !x.is_done && !picked.includes(x)) ?? null
      : null;
    await change(`Carried ${n} ${n === 1 ? "to-do" : "to-dos"} forward to the week of ${fmtDay(to)}`, async () => {
      let added = 0;
      for (const t of picked) {
        const old = fwdSlots.filter((x) => x.todo_id === t.id);
        for (const s of old.filter((x) => x.planned_on < to && !x.entry_id && !x.is_cancelled)) {
          await saveSlot(s.id, { is_cancelled: true, cancelled_by_sync: false });
        }
        if (targetEmail && isEmail(t)) {
          // its unspent hours join that week's email check; it closes on what was logged
          const logged = await loggedHoursOf(old.filter((x) => x.entry_id).map((x) => x.entry_id!));
          added += Math.max(0, (t.est_hours ?? 0) - logged);
          await saveTodo(t.id, { est_hours: Math.round(logged * 100) / 100, is_done: true, done_at: new Date().toISOString() });
        } else {
          await saveTodo(t.id, { due_on: to });
        }
      }
      if (targetEmail && added > 0) {
        await saveTodo(targetEmail.id, { est_hours: Math.round(((targetEmail.est_hours ?? 0) + added) * 100) / 100 });
      }
    });
  }
  /** What a row in the carry-forward list says about its to-do. */
  function fwdInfo(r: FwdRow): string {
    const days = r.loggedDays ? `${r.loggedDays} ${r.loggedDays === 1 ? "day" : "days"} logged` : "";
    return [label(r.t), r.t.est_hours ? `est. ${fmtHours(r.t.est_hours)}` : "", days].filter(Boolean).join(" · ");
  }

  // ---- email checks: one to-do for the week, a card on each ticked day ---------------------
  // One to-do holding the week's email time, so a day's card moves (and merges)
  // like any other, and time logged on one day comes off the days still to do.
  const EMAIL_TITLE = "Email check";
  const weekdays = $derived(days.filter((d) => { const w = parse(d).getDay(); return w >= 1 && w <= 5; }));
  let emailPick = $state<Record<string, boolean>>({});
  let emailHours = $state(1.5);
  let emailCategory = $state("");

  const isEmail = (t: { title: string } | undefined) => t?.title.trim().toLowerCase() === EMAIL_TITLE.toLowerCase();
  function hasEmailCheck(d: string): boolean {
    return weekSlots.some((x) => x.planned_on === d && !x.is_cancelled && isEmail(todoById.get(x.todo_id)));
  }
  // this week's email-check to-dos, earliest first: one, or several made separately before checks were joined
  const emailTodos = $derived(
    tasks.filter((t) => isEmail(t) && !t.is_cancelled && weekSlots.some((s) => s.todo_id === t.id))
      .sort((a, b) => a.due_on.localeCompare(b.due_on) || a.id.localeCompare(b.id)),
  );

  /**
   * Join separate email checks into one to-do: every day's card (logged ones
   * too) moves under the first, whose total becomes the sum of theirs. A card
   * without hours of its own takes its old to-do's estimate as its share.
   */
  async function joinEmailChecks() {
    const list = emailTodos;
    if (list.length < 2) return;
    const [keep, ...rest] = list;
    const total = list.reduce((s, t) => s + (t.est_hours ?? 0), 0);
    const weightOf = (t: Todo, s: Slot) =>
      s.planned_hours === null && t.est_hours !== null && slotsOf(t).filter((x) => !x.is_cancelled).length === 1
        ? { planned_hours: t.est_hours } : {};
    panel = null;
    await change(`Joined ${list.length} email checks into one`, async () => {
      for (const s of slotsOf(keep)) {
        const w = weightOf(keep, s);
        if ("planned_hours" in w) await saveSlot(s.id, w);
      }
      for (const t of rest) {
        for (const s of slotsOf(t)) await saveSlot(s.id, { todo_id: keep.id, ...weightOf(t, s) });
        await deleteTodo(t.id);
      }
      const done = list.every((t) => t.is_done);
      await saveTodo(keep.id, { est_hours: total || null, is_done: done, done_at: done ? keep.done_at : null });
    });
  }
  function openEmail() {
    emailPick = Object.fromEntries(weekdays.map((d) => [d, !hasEmailCheck(d)]));
    emailHours = 1.5;
    emailCategory = tax?.categories.find((c) => c.code === "ADM_MAIL")?.id
      ?? tax?.categories.find((c) => c.kind === "email")?.id ?? "";
    panel = { kind: "email" };
  }
  async function createEmailChecks() {
    const picked = weekdays.filter((d) => emailPick[d]);
    // days added to a week that already has one email check join it, rather than starting another
    const into = emailTodos.length === 1 ? emailTodos[0] : null;
    if (picked.length) await change(`Added ${picked.length} email ${picked.length === 1 ? "check" : "checks"}`, async () => {
      const id = into
        ? (await saveTodo(into.id, { est_hours: (into.est_hours ?? 0) + emailHours * picked.length, is_done: false, done_at: null }))
        : await saveTodo(null, {
            kind: "task", title: EMAIL_TITLE, due_on: picked[0], category_id: emailCategory || null,
            est_hours: emailHours * picked.length, must_this_week: false,
          });
      for (const d of picked) await saveSlot(null, { todo_id: id, planned_on: d, planned_hours: emailHours });
    });
    panel = null;
  }

  // Hours on each open card (not logged, not cancelled) of a task: what is left
  // of its estimate after everything logged, shared over the open cards in
  // proportion to their own planned hours (see share.ts). So the days still to
  // do follow the estimate, and grow or shrink as logged days come in under or
  // over their plan.
  const openHours = $derived.by(() => {
    const out = new Map<string, number | null>();
    for (const t of todos) {
      if (t.kind !== "task") continue;
      const open = slotsOf(t).filter((x) => !x.entry_id && !x.is_cancelled);
      for (const [id, h] of shareRemaining(t.est_hours, loggedFor(t), open, today())) out.set(id, h);
    }
    return out;
  });

  /** Hours planned for this card: an open card's share of what is left; a logged or
   *  cancelled one keeps its own figure, or the to-do's estimate when it has just one day. */
  function cardHours(s: Slot, t: Todo): number | null {
    if (t.kind === "task" && openHours.has(s.id)) return openHours.get(s.id)!;
    if (s.planned_hours !== null) return s.planned_hours;
    const live = slotsOf(t).filter((x) => !x.is_cancelled);
    return live.length === 1 ? t.est_hours : null;
  }

  // ---- show logged entries on the days ------------------------------------------------
  function savedShowLogged(): boolean {
    try { return localStorage.getItem(SHOW_LOGGED) !== "0"; } catch { return true; }
  }
  let showLogged = $state(savedShowLogged());
  $effect(() => {
    try { localStorage.setItem(SHOW_LOGGED, showLogged ? "1" : "0"); } catch {}
  });

  // ---- import meeting invites (.ics) --------------------------------------------------
  type Candidate = Meeting & { pick: boolean; dupe: boolean };
  let candidates = $state<Candidate[]>([]);
  let importCategory = $state("");
  let importNote = $state("");
  let importing = $state(false);

  async function readFiles(event: Event) {
    const files = [...((event.target as HTMLInputElement).files ?? [])];
    const found: Meeting[] = [];
    for (const f of files) found.push(...meetingsInRange(await f.text(), start, end));
    // the same occurrence from two files counts once
    const seen = new Set<string>();
    const unique = found.filter((m) => {
      const k = `${m.uid}|${m.date}|${m.start}`;
      return seen.has(k) ? false : (seen.add(k), true);
    });
    const existing = new Set(
      weekSlots
        .filter((s) => todoById.get(s.todo_id)?.kind === "meeting")
        .map((s) => `${todoById.get(s.todo_id)!.title.toLowerCase()}|${s.planned_on}|${s.start_time?.slice(0, 5)}`),
    );
    candidates = unique.map((m) => {
      const dupe = existing.has(`${m.title.toLowerCase()}|${m.date}|${m.start}`);
      return { ...m, dupe, pick: !dupe };
    });
    importNote = files.length && !unique.length ? "No timed meetings in this week in that file." : "";
    if (!importCategory) {
      importCategory = tax?.categories.find((c) => c.code === "RES_MEET")?.id ?? "";
    }
  }

  async function importPicked() {
    const picked = candidates.filter((c) => c.pick);
    if (!picked.length) return;
    importing = true;
    const label = `Imported ${picked.length} ${picked.length === 1 ? "meeting" : "meetings"}`;
    try {
      await undoable(label, async () => {
      for (const m of picked) {
        const [sh, sm] = m.start.split(":").map(Number);
        const [eh, em] = m.end.split(":").map(Number);
        const len = Math.round(((eh * 60 + em - sh * 60 - sm) / 60) * 100) / 100;
        const id = await saveTodo(null, {
          kind: "meeting", title: m.title, due_on: m.date, category_id: importCategory || null,
          est_hours: len, must_this_week: true, note: m.location || null,
        });
        await saveSlot(null, { todo_id: id, planned_on: m.date, start_time: m.start, end_time: m.end, planned_hours: len });
      }
      });
      importNote = `Added ${picked.length} ${picked.length === 1 ? "meeting" : "meetings"}.`;
      showToast(label, true);
      candidates = [];
      await load();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      importing = false;
    }
  }

  const dayName = (d: string) => parse(d).toLocaleDateString("en-GB", { weekday: "short" });
  const dayNum = (d: string) => parse(d).getDate();
  const hhmm = (t: string | null) => (t ? t.slice(0, 5) : "");
</script>

<section class="week">
  <span class="eyebrow">Week</span>
  <h1>Plan the week</h1>

  <div class="nav">
    <button onclick={() => (offset -= 1)} aria-label="Previous week">‹</button>
    <strong>{fmtDay(start)} – {fmtDay(end)}</strong>
    <button onclick={() => (offset += 1)} aria-label="Next week">›</button>
    {#if !isCurrent}<button class="link" onclick={() => (offset = 0)}>This week</button>{/if}
    {#if loading}<span class="muted small">loading…</span>{/if}
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  <div class="week-totals" aria-label="Week totals">
    <div class="wt" title="On the calendar, plus must-dos not placed on a day yet">
      <span class="wt-label">Planned</span>
      <span class="wt-value">{fmtHours(weekTotals.planned)}</span>
      <span class="wt-sub">
        calendar {fmtHours(weekTotals.calendar)} + must-dos {fmtHours(weekTotals.must.hours)}{weekTotals.unknown ? ` · +${weekTotals.unknown} without hours` : ""}
      </span>
    </div>
    <div class="wt" title="Flexible to-dos not on the calendar: not counted as planned">
      <span class="wt-label">Flexible</span>
      <span class="wt-value">{fmtHours(weekTotals.flex.hours)}</span>
      <span class="wt-sub">
        {weekTotals.flex.count} {weekTotals.flex.count === 1 ? "to-do" : "to-dos"}{weekTotals.flex.unknown ? ` · ${weekTotals.flex.unknown} without hours` : ""}
      </span>
    </div>
    <div class="wt">
      <span class="wt-label">Logged</span>
      <span class="wt-value">{fmtHours(weekTotals.logged)}</span>
      {#if weekTotals.target}<span class="wt-sub">{Math.round((100 * weekTotals.logged) / weekTotals.target)}% of target</span>{/if}
    </div>
    {#if weekTotals.target}
      <div class="wt">
        <span class="wt-label">Weekly target</span>
        <span class="wt-value">{fmtHours(weekTotals.target)}</span>
        <span class="wt-sub">
          {#if weekTotals.planned >= weekTotals.target}planned covers it{:else}{fmtHours(weekTotals.target - weekTotals.planned)} not yet planned{/if}
        </span>
      </div>
    {/if}
  </div>

  <p class="summary">
    Meetings <strong>{fmtHours(summary.meetingH)}</strong> ·
    open duties <strong>{fmtHours(summary.dutyH)}</strong> ·
    logged <strong>{fmtHours(summary.logged)}</strong>
    {#if summary.mustAll} · must-dos <strong>{summary.mustDone}/{summary.mustAll}</strong> done{/if}
    {#if summary.tentativeH} · tentative <strong>{fmtHours(summary.tentativeH)}</strong> (not counted){/if}
  </p>

  <div class="toolbar">
    <button class="primary" onclick={() => openEntry(null, isCurrent ? today() : start)}>+ Log</button>
    <button onclick={() => (panel = { kind: "todo", todo: null, as: "task" })}>+ To-do</button>
    <button onclick={openMilestones} title="To-dos from milestones that fall in this week">+ From milestones</button>
    <button onclick={() => (panel = { kind: "todo", todo: null, as: "meeting", day: isCurrent ? today() : start })}>+ Meeting</button>
    <label class="toggle"><input type="checkbox" bind:checked={showLogged} /> Show logged time</label>
  </div>
  <div class="outlook-bar">
    {#if feed?.ics_url}
      <span class="muted">Outlook · {syncing ? "syncing…" : syncedAt(feed)}{syncNote ? ` · ${syncNote}` : ""}</span>
      <button class="mini" disabled={syncing} onclick={runSync}>Sync now</button>
      <button class="mini" onclick={() => (panel = { kind: "outlook" })}>Settings</button>
    {:else}
      <button class="mini" onclick={() => (panel = { kind: "outlook" })}>Connect Outlook calendar…</button>
    {/if}
  </div>

  {#if inbox.todos.length && tax}
    <details class="inbox-wrap" open>
      <summary><h2>From Outlook — to review ({inbox.todos.length})</h2></summary>
      <OutlookInbox todos={inbox.todos} slots={inbox.slots} {tax} {projects} onchange={load} {remember} />
    </details>
  {/if}

  <!-- ================= days ================= -->
  <div class="days">
    {#each days as d (d)}
      {@const meetings = slotsOn(d, "meeting")}
      {@const duties = slotsOn(d, "task")}
      {@const plan = plannedOn(d)}
      <div class="day" class:today={d === today()} class:past={d < today()}>
        <div class="day-head">
          <span class="dname">{dayName(d)} <span class="dnum">{dayNum(d)}</span></span>
          <span class="day-hours small">
            {#if plan.hours || plan.unknown}<span class="planned" title="Meetings and duties planned for this day">{fmtHours(plan.hours)} planned{plan.unknown ? ` · +${plan.unknown} without hours` : ""}</span>{/if}
            {#if loggedOn(d)}<span class="muted">{fmtHours(loggedOn(d))} logged</span>{/if}
          </span>
        </div>

        {#each meetings as s (s.id)}
          {@const t = todoById.get(s.todo_id)!}
          <div class="card meeting" class:logged={!!s.entry_id} class:cancelled={s.is_cancelled} class:review={pending(t)}
               class:tentative={tentative(t)}
               role="group" oncontextmenu={(ev) => openMenu(ev, s, d)}>
            <button class="card-body" aria-haspopup="menu" title="Actions (click or right-click)"
                    onclick={(ev) => openMenu(ev, s, d)}>
              <span class="time">{hhmm(s.start_time)}–{hhmm(s.end_time)}</span>
              <span class="title">{t.is_core ? "🎯 " : ""}{t.title}</span>
              {#if label(t)}<span class="sub">{label(t)}</span>{/if}
              {#if s.is_cancelled}<span class="off">cancelled</span>{:else if s.entry_id}<span class="ok">✓ logged</span>{:else if pending(t)}<span class="off">from Outlook — to review{t.source_tentative ? " · tentative" : ""}</span>{:else if tentative(t)}<span class="off">tentative</span>{/if}
            </button>
          </div>
        {/each}

        {#each duties as s (s.id)}
          {@const t = todoById.get(s.todo_id)!}
          {@const e = s.entry_id ? entryById.get(s.entry_id) : null}
          {@const h = cardHours(s, t)}
          <div class="card duty" class:logged={!!s.entry_id} class:done={t.is_done}
               class:cancelled={s.is_cancelled} class:review={pending(t)} class:tentative={tentative(t)}
               class:stale={!s.entry_id && !s.is_cancelled && !t.is_done && d < today()}
               role="group" oncontextmenu={(ev) => openMenu(ev, s, d)}>
            <button class="card-body" aria-haspopup="menu" title="Actions (click or right-click)"
                    onclick={(ev) => openMenu(ev, s, d)}>
              <span class="title">{t.must_this_week ? "● " : ""}{t.is_core ? "🎯 " : ""}{t.title}</span>
              {#if label(t) || h}<span class="sub">{label(t)}{label(t) && h ? " · " : ""}{h ? fmtHours(h) : ""}</span>{/if}
              {#if s.is_cancelled}<span class="off">cancelled</span>{:else if s.entry_id}<span class="ok">✓ {e ? fmtHours(e.minutes / 60) : "logged"}</span>{:else if pending(t)}<span class="off">from Outlook — to review</span>{:else if tentative(t)}<span class="off">tentative</span>{:else if t.is_done}<span class="ok">done</span>{:else if d < today() && h === 0 && t.est_hours !== null}<span class="off">not logged — hours moved on</span>{/if}
            </button>
          </div>
        {/each}

        {#if showLogged}
          {#each entriesOn(d) as e (e.id)}
            <button class="entry" title={e.description ?? "Edit this entry"} onclick={() => openEntry(e, d)}>
              <span class="time">{e.ended_at ? `${e.started_at.slice(11, 16)}–${e.ended_at.slice(11, 16)}` : `${e.manual_minutes} min`}</span>
              {e.is_core ? "🎯 " : ""}{label(e)}
            </button>
          {/each}
        {/if}

        <div class="add-day">
          <button onclick={() => openEntry(null, d)}>+ log</button>
          <button onclick={() => (panel = { kind: "todo", todo: null, as: "meeting", day: d })}>+ meeting</button>
          <button onclick={() => (panel = { kind: "todo", todo: null, as: "task", day: d, place: true })}>+ to-do</button>
        </div>
      </div>
    {/each}
  </div>
  <div class="below-days">
    <button onclick={openEmail}>✉ Create email checks (Mon–Fri)</button>
    <button onclick={() => openForward()}>↪ Carry forward unfinished to-dos…</button>
  </div>

  <!-- ================= to-do list ================= -->
  <h2>To-dos not yet on a day</h2>
  {#if !tasks.length}
    <p class="muted">No to-dos for this week yet.</p>
  {:else if !unplaced.length}
    <p class="muted">Everything for this week is on the calendar.</p>
  {/if}
  {#each groups as g (g.key)}
    {#if g.rows.length}
      {@const gh = g.key === "done" ? null : listHours(g.key as "must" | "flex")}
      <div class="group" class:muted-group={g.key === "done"}>
        <h3>{g.title} <span class="muted small">{g.rows.length}{gh && gh.hours ? ` · ${fmtHours(gh.hours)}` : ""}</span></h3>
        <ul class="todos">
          {#each g.rows as t (t.id)}
            {@const ts = slotsOf(t)}
            {@const lh = loggedFor(t)}
            <li class="todo" class:cancelled={t.is_cancelled}>
              {#if t.is_cancelled}
                <span class="x-mark" aria-hidden="true">⊘</span>
              {:else}
                <input type="checkbox" checked={t.is_done} aria-label="Done" onchange={(ev) => setDone(t, (ev.target as HTMLInputElement).checked)} />
              {/if}
              <div class="t-main">
                <button class="t-title" onclick={() => (panel = { kind: "todo", todo: t })}>
                  {t.is_core ? "🎯 " : ""}{t.title}
                </button>
                <span class="t-meta muted">
                  {label(t)}{label(t) && (t.est_hours || lh) ? " · " : ""}
                  {#if lh}{fmtHours(lh)}{t.est_hours ? ` of ${fmtHours(t.est_hours)}` : ""} logged{:else if t.est_hours}est. {fmtHours(t.est_hours)}{/if}
                </span>
                {#if ts.length}
                  <span class="t-days">
                    {#each ts as s (s.id)}
                      <span class="daychip" class:logged={!!s.entry_id} class:cancelled={s.is_cancelled}>{dayName(s.planned_on)} {dayNum(s.planned_on)}{s.entry_id ? " ✓" : ""}</span>
                    {/each}
                  </span>
                {/if}
              </div>
              <div class="t-acts">
                {#if t.is_cancelled}
                  <span class="muted small">cancelled</span>
                  <button class="mini" onclick={() => restore(t)}>Restore</button>
                  <button class="mini danger" title="Delete for good" onclick={() => deleteWhole(t)}>Delete</button>
                {:else if !t.is_done}
                  <select aria-label="Plan on a day" onchange={(ev) => { const el = ev.target as HTMLSelectElement; if (el.value) placeOn(t, el.value); el.value = ""; }}>
                    <option value="">Plan on…</option>
                    {#each days as d (d)}<option value={d}>{dayName(d)} {dayNum(d)}</option>{/each}
                  </select>
                  <button class="mini" onclick={() => openSpread(t)}>Plan across days…</button>
                  <button class="mini" onclick={() => openLog(t, null, isCurrent ? today() : start)}>✓ Log</button>
                  <button class="mini" title={t.must_this_week ? "Make flexible" : "Make a must-do"} onclick={() => setMust(t)}>{t.must_this_week ? "→ flexible" : "→ must"}</button>
                  <button class="mini" title="Cancel — stays here, struck through" onclick={() => cancelTodo(t)}>Cancel</button>
                  <button class="mini danger" title="Delete for good" aria-label="Delete" onclick={() => deleteWhole(t)}>✕</button>
                {:else}
                  <button class="mini danger" title="Delete for good" aria-label="Delete" onclick={() => deleteWhole(t)}>✕</button>
                {/if}
              </div>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  {/each}

  <!-- ================= to think about ================= -->
  {#snippet linked(text: string)}{#each linkParts(text) as part, i (i)}{#if part.url}<a class="ulink" href={part.url} target="_blank" rel="noopener" title={part.url}>link</a>{:else}{part.text}{/if}{/each}{/snippet}
  {#snippet noteBox(t: Todo)}
    <div class="note-box">
      <textarea rows="3" bind:value={noteText} placeholder="Develop it — notes, options, who to ask…" aria-label="Note"
                onkeydown={(ev) => noteKeys(ev, t)}></textarea>
      {#if noteError}<p class="error">Not saved: {noteError}</p>{/if}
      <div class="t-acts">
        <button class="mini primary" onclick={() => saveNote(t)} disabled={!noteText.trim()}>Save</button>
        <button class="mini" onclick={stopNote}>Cancel</button>
        <span class="muted small">Ctrl+Enter saves</span>
      </div>
    </div>
  {/snippet}
  <div class="group ideas">
    <h3>To think about {#if ideas.length}<span class="muted small">{ideas.length}</span>{/if}</h3>
    <form class="idea-add" onsubmit={addIdea}>
      <input bind:value={ideaText} placeholder="Jot down a thought — paste a web address and it shows as a short “link”" aria-label="New idea" />
      <button type="submit" disabled={!ideaText.trim()}>Add</button>
    </form>
    <ul class="todos">
      {#each shownIdeas as t (t.id)}
        <li class="idea" class:dragging={dragId === t.id} data-id={t.id}>
          {#if ideaEditing === t.id}
            <div class="idea-edit">
              <input bind:value={ideaDraft.title} aria-label="Idea"
                     onkeydown={(ev) => { if (ev.key === "Enter") saveIdea(t); else ideaKeys(ev, t); }} />
              {#if t.note}
                <textarea rows="3" bind:value={ideaDraft.note} aria-label="Note" onkeydown={(ev) => ideaKeys(ev, t)}></textarea>
              {/if}
              {#if ideaError}<p class="error">Not saved: {ideaError}</p>{/if}
              <div class="t-acts">
                <button class="mini primary" onclick={() => saveIdea(t)}>Save</button>
                <button class="mini" onclick={() => (ideaEditing = null)}>Cancel</button>
              </div>
            </div>
          {:else}
            <button class="grip" title="Drag to reorder (or use ↑ ↓)" aria-label={`Move “${t.title}”: drag, or press up or down`}
                    onpointerdown={(ev) => startDrag(ev, t)}
                    onkeydown={(ev) => keyMove(ev, t)}>⠿</button>
            <div class="t-main">
              <span class="idea-title">{@render linked(t.title)}</span>
              {#if t.note}<span class="idea-note">{@render linked(t.note)}</span>{/if}
              <span class="t-meta muted">jotted {fmtDay(t.due_on)}</span>
              {#if notesOf(t).length}
                <ul class="inotes">
                  {#each notesOf(t) as n (n.id)}
                    <li>
                      {#if noteEditing === n.id}
                        {@render noteBox(t)}
                      {:else}
                        <span class="idea-note">{@render linked(n.body)}</span>
                        <span class="t-meta muted">{fmtDay(n.created_at.slice(0, 10))}</span>
                        <button class="link" onclick={() => startNote(t, n)}>edit</button>
                        <button class="link danger" aria-label="Delete note" title="Delete note" onclick={() => deleteNote(t, n)}>✕</button>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}
              {#if noteFor === t.id}{@render noteBox(t)}{/if}
            </div>
            <div class="t-acts">
              <button class="mini" title="Add a note to develop it" onclick={() => startNote(t)}>+ Note</button>
              <button class="mini" title="Edit the idea" onclick={() => editIdea(t)}>Edit</button>
              <button class="mini" title="Make it a to-do for this week" onclick={() => ideaToTodo(t)}>→ To-do</button>
              <button class="mini" title="Thought through — take it off the list" onclick={() => ideaDone(t)}>Done</button>
              <button class="mini danger" aria-label="Delete" title="Delete" onclick={() => deleteIdea(t)}>✕</button>
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  </div>

  <!-- ================= invites ================= -->
  <details class="import">
    <summary><h2>Import meeting invites</h2></summary>
    <p class="muted small">
      Choose one or more <code>.ics</code> files — an invite attachment, or your calendar exported from Outlook.
      Timed meetings in {fmtDay(start)} – {fmtDay(end)} are listed for you to pick; ones already on the plan are unticked.
    </p>
    <div class="import-row">
      <input type="file" accept=".ics,text/calendar" multiple onchange={readFiles} />
      {#if tax}
        <label>Category
          <select bind:value={importCategory}>
            <option value="">— none —</option>
            {#each tax.areas as a (a.id)}
              <optgroup label={a.label}>
                {#each tax.categories.filter((c) => c.area_id === a.id) as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
              </optgroup>
            {/each}
          </select>
        </label>
      {/if}
    </div>
    {#if candidates.length}
      <ul class="candidates">
        {#each candidates as c, i (c.uid + c.date + c.start + i)}
          <li>
            <label>
              <input type="checkbox" bind:checked={c.pick} />
              <span class="time">{dayName(c.date)} {dayNum(c.date)} · {c.start}–{c.end}</span>
              {c.title}
              {#if c.dupe}<span class="muted small">(already on the plan)</span>{/if}
            </label>
          </li>
        {/each}
      </ul>
      <button class="primary" onclick={importPicked} disabled={importing || !candidates.some((c) => c.pick)}>
        Add {candidates.filter((c) => c.pick).length} to the plan
      </button>
    {/if}
    {#if importNote}<p class="muted small">{importNote}</p>{/if}
  </details>
</section>

<svelte:window onkeydown={keys} onresize={closeMenu} onscroll={closeMenu} />

{#if toast}
  <div class="toast" role="status">
    <span>{toast.text}</span>
    {#if toast.canUndo}<button onclick={() => { toast = null; undoLast(); }}>Undo</button>{/if}
    <button class="x" aria-label="Dismiss" onclick={() => (toast = null)}>✕</button>
  </div>
{/if}

{#if menu}
  {@const m = menu}
  <div class="menu-backdrop" role="presentation" onclick={closeMenu}
       oncontextmenu={(ev) => { ev.preventDefault(); closeMenu(); }}></div>
  <div class="menu" role="menu" style:left={`${m.x}px`} style:top={`${m.y}px`} use:focusFirst>
    {#each menuItems(m) as item (item.label)}
      <button role="menuitem" class:danger={item.danger} onclick={() => { closeMenu(); item.run(); }}>{item.label}</button>
    {/each}
  </div>
{/if}

<dialog bind:this={dialog} onclose={() => (panel = null)}>
  {#if panel && tax}
    {#if panel.kind === "todo"}
      <h2>{panel.todo ? `Edit ${panel.todo.kind === "meeting" ? "meeting" : "to-do"}` : panel.as === "meeting" ? "New meeting" : "New to-do"}</h2>
      <TodoForm todo={panel.todo} slots={panel.todo ? slotsOf(panel.todo) : []} {tax} {projects}
                weekStart={start} day={panel.day} placeOnDay={panel.place} kind={panel.as}
                onsaved={closed} oncancel={() => (panel = null)} />
    {:else if panel.kind === "spread"}
      {@const t = panel.todo}
      <h2>Plan “{t.title}” across days</h2>
      <div class="pick">
        <div class="pick-days">
          {#each days as d (d)}
            {@const lockedIn = slotsOf(t).some((x) => x.planned_on === d && !!x.entry_id)}
            <label class:locked={lockedIn} title={lockedIn ? "Already logged — stays planned" : ""}>
              <input type="checkbox" bind:checked={spreadPick[d]} disabled={lockedIn} />
              {dayName(d)} {dayNum(d)}
            </label>
          {/each}
        </div>
        <label class="pick-hours">Total hours <input type="number" min="0" step="0.5" bind:value={spreadHours} /></label>
        <p class="muted small">
          {#if !spreadDays.length}Tick at least one day.
          {:else if perDay}{fmtHours(spreadHours ?? 0)} over {spreadDays.length} {spreadDays.length === 1 ? "day" : "days"} = <strong>{fmtHours(perDay)}</strong> a day.
          {:else}No hours given: the days are planned without hours.{/if}
          Unticking a day takes it off the calendar.
        </p>
        <div class="pick-actions">
          <button class="primary" disabled={!spreadDays.length} onclick={() => saveSpread(t)}>Save plan</button>
          <button onclick={() => (panel = null)}>Cancel</button>
        </div>
      </div>
    {:else if panel.kind === "milestones"}
      <h2>To-dos from milestones · {fmtDay(start)} – {fmtDay(end)}</h2>
      <div class="pick">
        {#if msLoading}
          <p class="muted">Loading…</p>
        {:else if !msRows.length}
          <p class="muted">No milestones fall in this week. Milestones need dates (or their project's) to show here.</p>
        {:else}
          <p class="muted small">
            Hours suggested are this week's share of what is left, spread evenly to the due date. Overdue and
            due-this-week milestones are ticked for you.
          </p>
          <div class="ms-groups">
            {#each msGroups as g (g.key)}
              {@const all = g.projects.flatMap((x) => x.rows)}
              <details class="ms-group" open={msOpen[g.key] ?? false}
                       ontoggle={(ev) => (msOpen[g.key] = (ev.currentTarget as HTMLDetailsElement).open)}>
                <summary>
                  <strong>{g.label}</strong>
                  <span class="muted">{all.length} {all.length === 1 ? "milestone" : "milestones"}{pickedIn(all) ? ` · ${pickedIn(all)} ticked` : ""}</span>
                </summary>
                {#each g.projects as gp (gp.p.id)}
                  <div class="ms-project">
                    <div class="ms-project-head">
                      <span>{gp.p.name}</span>
                      <button class="mini" onclick={() => pickAll(gp.rows, true)}>all</button>
                      <button class="mini" onclick={() => pickAll(gp.rows, false)}>none</button>
                    </div>
                    <ul class="ms-pick">
                      {#each gp.rows as r (r.m.id)}
                        <li class:off={!!r.existing && !r.pick}>
                          <input type="checkbox" bind:checked={r.pick} aria-label={`Add ${r.m.title}`} />
                          <div class="ms-what">
                            <strong>{r.m.title}</strong>
                            <span class="ms-when" class:late={r.info.overdue}>
                              {#if r.info.overdue}overdue since {fmtDay(r.info.due!)}
                              {:else if r.info.due}due {fmtDay(r.info.due)}{r.m.due_on ? "" : " (project end)"}
                              {:else}no due date{/if}
                              {#if r.m.hard_deadline} · hard deadline{/if}
                              {#if r.info.remaining !== null} · {fmtHours(r.info.remaining)} left{:else} · no planned hours{/if}
                              {#if r.existing}
                                <span class="ms-existing">· already a to-do this week: “{r.existing.title}” — tick to add another</span>
                              {/if}
                            </span>
                          </div>
                          <label class="ms-h">h <input type="number" min="0" step="0.5" bind:value={r.hours} aria-label="Hours this week" /></label>
                          <label class="ms-must"><input type="checkbox" bind:checked={r.must} /> must</label>
                        </li>
                      {/each}
                    </ul>
                  </div>
                {/each}
              </details>
            {/each}
          </div>
        {/if}
        <div class="pick-actions">
          {#if msRows.some((r) => r.pick)}
            {@const n = msRows.filter((r) => r.pick).length}
            <button class="primary" onclick={addFromMilestones}>Add {n} to-{n === 1 ? "do" : "dos"}</button>
          {:else}
            <button class="primary" disabled>Tick milestones to add</button>
          {/if}
          <button onclick={() => (panel = null)}>Cancel</button>
        </div>
      </div>
    {:else if panel.kind === "moveTo"}
      {@const mv = panel}
      <h2>Move “{mv.todo.title}”</h2>
      <form class="move-to" onsubmit={(ev) => { ev.preventDefault(); const s = mv.slot; panel = null; moveTo(s, moveDate); }}>
        <label>To <input type="date" bind:value={moveDate} required /></label>
        <p class="muted small">
          Now on {fmtDay(mv.slot.planned_on)}. Any day will do, in this week or another; a to-do with no other day
          planned goes along to that week. If it is already planned on that day, the two join.
        </p>
        <div class="pick-actions">
          <button class="primary" type="submit" disabled={!moveDate || moveDate === mv.slot.planned_on}>Move</button>
          <button type="button" onclick={() => (panel = null)}>Cancel</button>
        </div>
      </form>
    {:else if panel.kind === "outlook"}
      <h2>Outlook calendar</h2>
      <OutlookSettings oncancel={() => (panel = null)}
                       onsaved={async (changed) => { panel = null; feed = await loadFeed(); if (changed && feed?.ics_url) runSync(); }} />
    {:else if panel.kind === "forward"}
      <h2>Carry forward unfinished to-dos</h2>
      <div class="pick">
        <label class="pick-hours">Into the week of
          <select value={fwdTo} onchange={(ev) => openForward((ev.target as HTMLSelectElement).value)}>
            <option value={start}>{fmtDay(start)} (on screen)</option>
            <option value={addDays(start, 7)}>{fmtDay(addDays(start, 7))} (the week after)</option>
          </select>
        </label>
        <p class="muted small">
          To-dos filed under any week before that one, neither done nor cancelled — choose the week after to send on
          the week on screen's leftovers. Tick the ones to bring; the rest stay where they are. A day planned for one
          before that week and never logged is cancelled (it stays on its day, struck through), so its hours move with
          the to-do.
        </p>
        {#if fwdLoading}
          <p class="muted">Loading…</p>
        {:else if !fwdRows.length}
          <p class="muted">Nothing unfinished before the week of {fmtDay(fwdTo)}.</p>
        {:else}
          <div class="small">
            <button class="link" onclick={() => fwdRows.forEach((r) => (r.pick = true))}>Tick all</button> ·
            <button class="link" onclick={() => fwdRows.forEach((r) => (r.pick = false))}>none</button>
          </div>
          {#each fwdWeeks as w (w)}
            <div class="fwd-week">
              <h3>Week of {fmtDay(w)}</h3>
              <ul class="fwd">
                {#each fwdRows.filter((r) => r.week === w) as r (r.t.id)}
                  <li>
                    <label>
                      <input type="checkbox" bind:checked={r.pick} />
                      <span>{r.t.must_this_week ? "● " : ""}{r.t.is_core ? "🎯 " : ""}{r.t.title}</span>
                      <span class="muted small">{fwdInfo(r)}</span>
                    </label>
                  </li>
                {/each}
              </ul>
            </div>
          {/each}
        {/if}
        <div class="pick-actions">
          {#if fwdRows.some((r) => r.pick)}
            <button class="primary" onclick={forwardPicked}>Carry {fwdRows.filter((r) => r.pick).length} forward</button>
          {:else}
            <button class="primary" disabled>Nothing ticked</button>
          {/if}
          <button onclick={() => (panel = null)}>Cancel</button>
        </div>
      </div>
    {:else if panel.kind === "email"}
      <h2>Create email checks</h2>
      <div class="pick">
        <p class="muted small">
          One “{EMAIL_TITLE}” to-do for the week, with a card on each ticked day. Move a card to another day like any
          to-do; time logged on one day comes off (or, if under, goes on to) the days still to do. Email time counts in
          equal shares to Teaching, Admin and Outreach, whichever Email category it is logged under.
        </p>
        {#if emailTodos.length > 1}
          <div class="join">
            <span class="small">This week's {emailTodos.length} email checks are separate to-dos, so their hours don't carry
              between days. Join them into one ({fmtHours(emailTodos.reduce((s, t) => s + (t.est_hours ?? 0), 0))} for the week)?</span>
            <button onclick={joinEmailChecks}>Join them into one</button>
          </div>
        {/if}
        <div class="pick-days">
          {#each weekdays as d (d)}
            {@const exists = hasEmailCheck(d)}
            <label class:locked={exists} title={exists ? "Already has an email check" : ""}>
              <input type="checkbox" bind:checked={emailPick[d]} disabled={exists} />
              {dayName(d)} {dayNum(d)}{exists ? " (already)" : ""}
            </label>
          {/each}
        </div>
        <div class="pick-row">
          <label class="pick-hours">Hours each day <input type="number" min="0" step="0.25" bind:value={emailHours} /></label>
          {#if tax}
            <label class="pick-hours">Category
              <select bind:value={emailCategory}>
                <option value="">— none —</option>
                {#each tax.areas as a (a.id)}
                  <optgroup label={a.label}>
                    {#each tax.categories.filter((c) => c.area_id === a.id) as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
                  </optgroup>
                {/each}
              </select>
            </label>
          {/if}
        </div>
        <div class="pick-actions">
          {#if weekdays.some((d) => emailPick[d])}
            {@const n = weekdays.filter((d) => emailPick[d]).length}
            <button class="primary" onclick={createEmailChecks}>Create {n} email {n === 1 ? "check" : "checks"} ({fmtHours(emailHours * n)})</button>
          {:else}
            <button class="primary" disabled>Nothing to create</button>
          {/if}
          <button onclick={() => (panel = null)}>Cancel</button>
        </div>
      </div>
    {:else if panel.kind === "entry"}
      {@const p = panel}
      <h2>{p.entry ? "Edit entry" : "Log time"}</h2>
      {#key p}
        <EntryForm entry={p.entry} {tax} {projects} defaults={entryDefaults(p.day)}
                   onsaved={(f, id, action) => entrySaved(p, f, id, action)} oncancel={() => (panel = null)} />
      {/key}
      {#if p.entry}
        {@const e = p.entry}
        {#if cvOpen}
          <div class="cv-add">
            <h3>CV achievement from this session</h3>
            <CvForm entry={null}
                    preset={{ source_type: "entry", entry_id: e.id, project_id: e.project_id, milestone_id: e.milestone_id,
                              entry_date: e.started_at.slice(0, 10),
                              title: e.description ?? (e.project_id ? projById.get(e.project_id)?.name ?? "" : "") }}
                    onsaved={() => (panel = null)} oncancel={() => (cvOpen = false)} />
          </div>
        {:else}
          <button class="cv-btn" onclick={() => (cvOpen = true)}>Add as CV achievement…</button>
        {/if}
      {/if}
    {:else}
      {@const p = panel}
      <h2>Log “{p.todo.title}”</h2>
      <EntryForm entry={null} {tax} {projects} defaults={logDefaults(p)} submitLabel="Log it"
                 onsaved={(f, id) => logged(p, f, id)} oncancel={() => (panel = null)} />
      <label class="mark-done"><input type="checkbox" bind:checked={markDone} /> Mark the {p.todo.kind === "meeting" ? "meeting" : "to-do"} done</label>
    {/if}
  {/if}
</dialog>

<style>
  .small { font-size: 0.8rem; }
  .nav { display: flex; align-items: center; gap: 0.6rem; font-family: var(--font-ui); margin: 0.6rem 0; flex-wrap: wrap; }
  .nav button { padding: 0.3rem 0.7rem; }
  .nav .link { background: none; border: none; color: var(--accent); text-decoration: underline; }
  .summary { font-family: var(--font-ui); font-size: 0.9rem; color: var(--ink-soft); margin: 0 0 0.8rem; }
  .week-totals { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: 0.6rem; margin: 0.4rem 0 0.7rem; font-family: var(--font-ui); max-width: 40rem; }
  .wt { display: grid; gap: 0.05rem; background: var(--panel); border-radius: var(--radius); padding: 0.55rem 0.8rem; }
  .wt-label { font-size: 0.75rem; color: var(--ink-soft); }
  .wt-value { font-size: 1.35rem; font-weight: 600; line-height: 1.2; }
  .wt-sub { font-size: 0.75rem; color: var(--ink-soft); }
  .summary strong { color: var(--ink); }
  .toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 1rem; font-family: var(--font-ui); }
  .toggle { display: inline-flex; align-items: center; gap: 0.4rem; margin-left: auto; font-size: 0.85rem; color: var(--ink-soft); }
  .toggle input { width: auto; }

  .days { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 0.5rem; font-family: var(--font-ui); }
  .day { background: var(--panel); border-radius: var(--radius); padding: 0.45rem; min-height: 9rem; display: flex; flex-direction: column; gap: 0.35rem; }
  .day.today { outline: 2px solid var(--accent); }
  .day-head { display: flex; justify-content: space-between; align-items: baseline; gap: 0.3rem; flex-wrap: wrap; }
  .dname { font-weight: 600; font-size: 0.85rem; }
  .dnum { font-size: 1.1rem; }
  .day.past .dname { color: var(--ink-soft); }
  .day-hours { display: grid; justify-items: end; line-height: 1.25; }
  .day-hours .planned { color: var(--ink); font-weight: 600; }

  .outlook-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin: -0.4rem 0 1rem; font-family: var(--font-ui); font-size: 0.82rem; }
  .inbox-wrap { margin-bottom: 1.2rem; }
  .inbox-wrap summary { cursor: pointer; margin-bottom: 0.6rem; }
  .inbox-wrap summary h2 { display: inline; font-size: 1.05rem; margin: 0; }
  .card.review { border-left-style: dashed; border-left-color: var(--ink-soft); opacity: 0.85; }
  .card.tentative { border-left-style: dotted; opacity: 0.8; }
  .below-days { display: flex; gap: 0.5rem; margin-top: 0.6rem; font-family: var(--font-ui); }
  .below-days button { font-size: 0.82rem; }
  .pick { display: grid; gap: 0.8rem; font-family: var(--font-ui); }
  .pick-days { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .pick-days label {
    display: inline-flex; align-items: center; gap: 0.35rem;
    border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.35rem 0.6rem; font-size: 0.88rem; cursor: pointer;
  }
  .pick-days label.locked { opacity: 0.6; cursor: default; }
  .pick-days input { width: auto; }
  .pick-row { display: flex; flex-wrap: wrap; gap: 1rem; }
  .pick-hours { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); max-width: 16rem; }
  .pick-actions { display: flex; gap: 0.5rem; }
  .join { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.8rem; padding: 0.6rem 0.7rem;
          border: 1px solid var(--rule); border-radius: var(--radius); background: var(--panel); }
  .join button { font-size: 0.82rem; }
  .fwd-week h3 { margin: 0.2rem 0 0.3rem; font-size: 0.82rem; color: var(--ink-soft); font-weight: 600; }
  .fwd { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.25rem; }
  .fwd label { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.45rem; font-size: 0.88rem; cursor: pointer; }
  .fwd input { width: auto; }
  .ms-groups { display: grid; gap: 0.4rem; max-height: 58vh; overflow-y: auto; padding-right: 0.2rem; }
  .ms-group { border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.3rem 0.6rem; }
  .ms-group summary { cursor: pointer; display: flex; gap: 0.6rem; align-items: baseline; flex-wrap: wrap; padding: 0.25rem 0; font-size: 0.9rem; }
  .ms-group summary .muted { font-size: 0.78rem; }
  .ms-project { margin: 0.3rem 0 0.5rem 0.4rem; }
  .ms-project-head { display: flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; font-weight: 600; color: var(--ink-soft); }
  .ms-pick { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.2rem; }
  .ms-pick li { display: grid; grid-template-columns: auto 1fr auto auto; gap: 0.6rem; align-items: center; padding: 0.4rem 0.3rem; border-bottom: 1px solid var(--rule); }
  .ms-pick li.off { opacity: 0.55; }
  .ms-pick input[type="checkbox"] { width: auto; }
  .ms-what { display: flex; flex-wrap: wrap; gap: 0.15rem 0.5rem; align-items: baseline; font-size: 0.88rem; }
  .ms-when { width: 100%; font-size: 0.78rem; color: var(--ink-soft); }
  .ms-when.late { color: var(--danger); }
  .ms-existing { color: var(--accent); }
  .ms-h { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; color: var(--ink-soft); }
  .ms-h input { width: 4.5rem; padding: 0.25rem 0.35rem; font-size: 0.85rem; }
  .ms-must { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.8rem; }
  @media (max-width: 40rem) { .ms-pick li { grid-template-columns: auto 1fr; } }
  .card-body {
    display: grid;
    gap: 0.1rem;
    width: 100%;
    min-width: 0;
    text-align: left;
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    color: inherit;
    cursor: pointer;
  }
  .card:hover { box-shadow: 0 0 0 1px var(--rule); }
  .menu-backdrop { position: fixed; inset: 0; z-index: 50; }
  .toast {
    position: fixed;
    left: 50%;
    bottom: 1.2rem;
    transform: translateX(-50%);
    z-index: 60;
    display: flex;
    align-items: center;
    gap: 0.8rem;
    max-width: calc(100vw - 32px);
    padding: 0.55rem 0.6rem 0.55rem 1rem;
    background: var(--ink);
    color: var(--paper);
    border-radius: var(--radius);
    box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
    font-family: var(--font-ui);
    font-size: 0.88rem;
  }
  .toast span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .toast button { background: none; border: 1px solid var(--paper); color: var(--paper); padding: 0.2rem 0.7rem; font-size: 0.82rem; }
  .toast button.x { border: none; padding: 0.2rem 0.4rem; opacity: 0.8; }
  .menu {
    position: fixed;
    z-index: 51;
    width: 220px;
    display: grid;
    padding: 0.25rem;
    background: var(--paper);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    box-shadow: 0 6px 20px rgb(0 0 0 / 0.18);
    font-family: var(--font-ui);
  }
  .menu button { text-align: left; background: none; border: none; border-radius: 4px; padding: 0.45rem 0.6rem; font-size: 0.85rem; }
  .menu button:hover, .menu button:focus-visible { background: var(--panel); outline: none; }
  .menu button.danger { color: var(--danger); }
  .card { background: var(--paper); border-radius: 4px; padding: 0.35rem 0.45rem; font-size: 0.78rem; display: grid; gap: 0.1rem; border-left: 3px solid var(--accent); }
  .card.duty { border-left-color: var(--ink-soft); }
  .card.logged { opacity: 0.7; }
  .card.done .title { text-decoration: line-through; color: var(--ink-soft); }
  .card.stale { border-left-color: var(--danger); }
  .card.cancelled { opacity: 0.55; border-left-color: var(--rule); }
  .card.cancelled .title, .card.cancelled .time { text-decoration: line-through; }
  .off { font-size: 0.72rem; color: var(--ink-soft); margin-right: auto; font-style: italic; }
  .card .time, .entry .time { font-variant-numeric: tabular-nums; font-weight: 600; }
  .card .title { font-weight: 500; overflow-wrap: anywhere; }
  .card .sub { color: var(--ink-soft); font-size: 0.72rem; }
  .mini { font-size: 0.72rem; padding: 0.1rem 0.4rem; }
  .ok { font-size: 0.72rem; color: var(--accent); margin-right: auto; }
  .entry {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    border-radius: 4px;
    padding: 0.1rem 0.2rem;
    font-size: 0.72rem;
    color: var(--ink-soft);
  }
  .entry:hover { background: var(--paper); color: var(--ink); }
  .cv-btn { margin-top: 0.9rem; font-size: 0.82rem; }
  .cv-add { margin-top: 1rem; border-top: 1px solid var(--rule); padding-top: 0.8rem; }
  .cv-add h3 { font-size: 0.92rem; font-family: var(--font-ui); }
  .add-day { margin-top: auto; display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.25rem; }
  .add-day button { font-size: 0.72rem; padding: 0.15rem; background: none; border: 1px dashed var(--rule); color: var(--ink-soft); }

  .week h2 { margin-top: 2rem; }
  .group { margin-top: 1rem; font-family: var(--font-ui); }
  .group h3 { font-size: 0.9rem; margin-bottom: 0.3rem; }
  .muted-group { opacity: 0.75; }
  .todos { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .todo { display: grid; grid-template-columns: auto 1fr auto; gap: 0.7rem; align-items: start; padding: 0.45rem 0.3rem; border-radius: var(--radius); }
  .todo:hover { background: var(--panel); }
  .todo > input { width: auto; margin-top: 0.25rem; }
  .t-main { display: grid; gap: 0.15rem; min-width: 0; }
  .t-title { background: none; border: none; padding: 0; text-align: left; font-size: 0.92rem; color: var(--ink); }
  .t-title:hover { text-decoration: underline; }
  .t-meta { font-size: 0.78rem; }
  .t-days { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .daychip { font-size: 0.7rem; border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.4rem; }
  .daychip.logged { border-color: var(--accent); color: var(--accent); }
  .daychip.cancelled { text-decoration: line-through; color: var(--ink-soft); }
  .t-acts { display: flex; gap: 0.3rem; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
  .t-acts select { width: auto; font-size: 0.78rem; padding: 0.15rem 0.3rem; }
  .todo.cancelled .t-title { text-decoration: line-through; color: var(--ink-soft); }
  .todo.cancelled .t-meta { opacity: 0.7; }
  .x-mark { color: var(--ink-soft); margin-top: 0.1rem; }
  .ideas { margin-top: 1.4rem; }
  .idea-add { display: flex; gap: 0.4rem; margin-bottom: 0.4rem; max-width: 46rem; }
  .idea-add input { flex: 1; }
  li.idea { display: grid; grid-template-columns: auto 1fr auto; gap: 0.5rem; align-items: start; padding: 0.45rem 0.3rem; border-radius: var(--radius); }
  li.idea.dragging { background: var(--panel); box-shadow: 0 2px 10px rgb(0 0 0 / 0.15); }
  .grip {
    background: none; border: none; padding: 0 0.2rem; font-size: 1rem; line-height: 1.3;
    color: var(--ink-soft); cursor: grab; touch-action: none; user-select: none;
  }
  .grip:active { cursor: grabbing; }
  li.idea:hover { background: var(--panel); }
  .idea-note { font-size: 0.82rem; white-space: pre-line; color: var(--ink); }
  .inotes { list-style: none; margin: 0.15rem 0 0; padding: 0 0 0 0.6rem; border-left: 2px solid var(--rule); display: grid; gap: 0.2rem; }
  .inotes li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.2rem 0.45rem; }
  .inotes .link { background: none; border: none; padding: 0; font-size: 0.75rem; color: var(--ink-soft); text-decoration: underline; cursor: pointer; }
  .inotes .link.danger { color: var(--danger); text-decoration: none; }
  .note-box { display: grid; gap: 0.3rem; width: 100%; max-width: 46rem; margin-top: 0.2rem; }
  .idea-title { font-size: 0.92rem; overflow-wrap: anywhere; }
  .ulink { text-decoration: underline; color: var(--accent); }
  .idea-edit { grid-column: 1 / -1; display: grid; gap: 0.4rem; max-width: 46rem; }
  .mini.danger { color: var(--danger); }

  .import { margin-top: 2rem; font-family: var(--font-ui); }
  .import summary { cursor: pointer; }
  .import summary h2 { display: inline; font-size: 1.1rem; }
  .import-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; margin: 0.5rem 0; }
  .import-row input[type="file"] { width: auto; border: none; padding: 0; }
  .import-row label { display: grid; gap: 0.2rem; font-size: 0.8rem; color: var(--ink-soft); min-width: 14rem; }
  .candidates { list-style: none; padding: 0; margin: 0.5rem 0; display: grid; gap: 0.2rem; font-size: 0.88rem; }
  .candidates label { display: flex; gap: 0.5rem; align-items: baseline; }
  .candidates input { width: auto; }
  .candidates .time { font-variant-numeric: tabular-nums; color: var(--ink-soft); min-width: 9rem; }

  dialog {
    width: min(46rem, calc(100vw - 32px));
    max-height: calc(100vh - 32px);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--paper);
    color: var(--ink);
    padding: 1.1rem 1.2rem;
  }
  dialog::backdrop { background: rgb(0 0 0 / 0.35); }
  dialog h2 { margin: 0 0 0.8rem; font-size: 1.1rem; }
  .mark-done { display: flex; align-items: center; gap: 0.45rem; margin-top: 0.8rem; font-family: var(--font-ui); font-size: 0.9rem; }
  .mark-done input { width: auto; }

  @media (max-width: 60rem) {
    .days { grid-template-columns: 1fr; }
    .day { min-height: 0; }
    .todo { grid-template-columns: auto 1fr; }
    .t-acts { grid-column: 2; justify-content: flex-start; }
  }
</style>
