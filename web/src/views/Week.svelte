<script lang="ts">
  import {
    loadTaxonomy, loadProjects, loadWeekPlan, loadEntriesBetween, saveSlot, deleteSlot, saveTodo, deleteTodo, fmtHours,
    saveEntry, deleteEntry, reinsertTodo, reinsertSlot, reinsertEntry, loadAllHours,
  } from "../lib/data";
  import type { Taxonomy, Project, Milestone, Todo, Slot, TimeEntry, TimeEntryFields } from "../lib/data";
  import { milestoneWeek } from "../lib/plan";
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
  let carried = $state<Set<string>>(new Set());
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
      const r = await syncOutlook();
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
    const [from, to, carry] = [start, end, isCurrent];
    loading = true;
    try {
      const [plan, logged, p, review] = await Promise.all([
        loadWeekPlan(from, to, carry), loadEntriesBetween(from, to), loadProjects(), loadUnreviewed(),
      ]);
      if (id !== request) return;
      projects = p;
      inbox = review;
      todos = plan.todos;
      slots = plan.slots;
      carried = plan.carried;
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
  // Each change made here records how to reverse it. Undo walks back through
  // them, most recent first; the bar at the bottom offers the latest one.
  type Step = { label: string; undo: () => Promise<unknown> };
  let history = $state<Step[]>([]);
  let toast = $state<{ text: string; canUndo: boolean } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | undefined;

  function showToast(text: string, canUndo: boolean) {
    toast = { text, canUndo };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 8000);
  }
  function remember(label: string, undo: () => Promise<unknown>) {
    history = [...history.slice(-29), { label, undo }];
    showToast(label, true);
  }
  async function undoLast() {
    const step = history[history.length - 1];
    if (!step) return;
    history = history.slice(0, -1);
    try {
      await step.undo();
      showToast(`Undone: ${step.label}`, false);
    } catch (e) {
      error = `Could not undo “${step.label}”: ${(e as Error).message}`;
    }
    await load();
  }
  /** Run a change; on success, remember how to undo it. */
  async function change(label: string, run: () => Promise<unknown>, undo: () => Promise<unknown>) {
    try {
      await run();
      remember(label, undo);
    } catch (e) {
      error = (e as Error).message;
    }
    await load();
  }
  const q = (t: { title: string }) => `“${t.title}”`;
  const snapTodo = (t: Todo): Todo => ({ ...$state.snapshot(t) }) as Todo;
  const snapSlot = (s: Slot): Slot => ({ ...$state.snapshot(s) }) as Slot;

  // ---- lookups -------------------------------------------------------------------
  const todoById = $derived(new Map(todos.map((t) => [t.id, t])));
  const catById = $derived(new Map((tax?.categories ?? []).map((c) => [c.id, c])));
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

  // ---- the week's to-do list ------------------------------------------------------
  const tasks = $derived(todos.filter((t) => t.kind === "task"));
  const live = $derived(tasks.filter((t) => !t.is_cancelled));
  // A to-do on a day this week shows on the calendar only; the list holds the
  // ones not placed yet. Cancelling its last day puts it back on the list.
  const onCalendar = $derived(new Set(weekSlots.filter((s) => !s.is_cancelled).map((s) => s.todo_id)));
  // Cancelled to-dos stay in their group, struck through, until restored or deleted.
  const unplaced = $derived(tasks.filter((t) => !onCalendar.has(t.id) && !pending(t)));
  const groups = $derived([
    // to-dos carried over from earlier weeks sit with this week's, marked "from week of …"
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
  function placeOn(t: Todo, day: string) {
    let id = "";
    return change(`Planned ${q(t)} on ${dayName(day)} ${dayNum(day)}`,
      async () => (id = await saveSlot(null, { todo_id: t.id, planned_on: day, planned_hours: null })),
      () => deleteSlot(id));
  }
  function move(s: Slot, by: number) {
    const t = todoById.get(s.todo_id)!;
    const to = addDays(s.planned_on, by);
    return change(`Moved ${q(t)} to ${dayName(to)} ${dayNum(to)}`,
      () => saveSlot(s.id, { planned_on: to }),
      () => saveSlot(s.id, { planned_on: s.planned_on }));
  }
  function unplan(s: Slot) {
    const t = todoById.get(s.todo_id);
    if (!t) return;
    if (t.kind === "meeting") {
      if (!confirm(`Delete the meeting “${t.title}”?${s.entry_id ? " Its logged time stays." : ""} (Use Edit to change its time.)`)) return;
      const todo = snapTodo(t);
      const own = slotsOf(t).map(snapSlot);
      return change(`Deleted the meeting ${q(t)}`, () => deleteTodo(t.id), () => reinsertTodo(todo, own));
    }
    if (s.entry_id && !confirm("This day was logged. Remove it from the plan? The logged time stays.")) return;
    const slot = snapSlot(s);
    return change(`Took ${q(t)} off ${dayName(s.planned_on)} ${dayNum(s.planned_on)}`,
      () => deleteSlot(s.id), () => reinsertSlot(slot));
  }
  // Cancelling keeps the card on its day, struck through, so the week still
  // shows what was planned; it can be restored. ✕ takes it off altogether.
  function setCancelled(s: Slot, cancelled: boolean) {
    const t = todoById.get(s.todo_id)!;
    return change(`${cancelled ? "Cancelled" : "Restored"} ${q(t)} on ${dayName(s.planned_on)} ${dayNum(s.planned_on)}`,
      () => saveSlot(s.id, { is_cancelled: cancelled }),
      () => saveSlot(s.id, { is_cancelled: !cancelled }));
  }
  function setDone(t: Todo, done: boolean) {
    const before = { is_done: t.is_done, done_at: t.done_at };
    return change(done ? `Marked ${q(t)} done` : `Reopened ${q(t)}`,
      () => saveTodo(t.id, { is_done: done, done_at: done ? new Date().toISOString() : null }),
      () => saveTodo(t.id, before));
  }
  function setMust(t: Todo) {
    const was = t.must_this_week;
    return change(`Made ${q(t)} ${was ? "flexible" : "a must-do"}`,
      () => saveTodo(t.id, { must_this_week: !was }),
      () => saveTodo(t.id, { must_this_week: was }));
  }
  function setTentative(t: Todo, on: boolean, keep = false) {
    const before = { is_tentative: t.is_tentative, reviewed: t.reviewed };
    return change(on ? `Marked ${q(t)} tentative` : `Confirmed ${q(t)}`,
      () => saveTodo(t.id, { is_tentative: on, ...(keep ? { reviewed: true } : {}) }),
      () => saveTodo(t.id, before));
  }
  function keepAsIs(t: Todo) {
    return change(`Kept ${q(t)}`, () => saveTodo(t.id, { reviewed: true }), () => saveTodo(t.id, { reviewed: false }));
  }
  async function ignoreEvent(t: Todo, s: Slot | null, all: boolean) {
    try {
      const undo = await dismissOutlook(snapTodo(t), s ? snapSlot(s) : null, all);
      remember(all ? `Ignored ${q(t)} and its repeats` : `Ignored ${q(t)}`, undo);
    } catch (e) {
      error = (e as Error).message;
    }
    await load();
  }
  function cancelTodo(t: Todo) {
    return change(`Cancelled ${q(t)}`,
      () => saveTodo(t.id, { is_cancelled: true }),
      () => saveTodo(t.id, { is_cancelled: false }));
  }
  function deleteWhole(t: Todo) {
    const logged = slotsOf(t).some((x) => x.entry_id);
    if (!confirm(`Delete “${t.title}”${slotsOf(t).length ? " and its planned days" : ""}?${logged ? " Logged time stays." : ""}`)) return;
    const todo = snapTodo(t);
    const own = slotsOf(t).map(snapSlot);
    return change(`Deleted ${q(t)}`, () => deleteTodo(t.id), () => reinsertTodo(todo, own));
  }
  function restore(t: Todo) {
    return change(`Restored ${q(t)}`,
      () => saveTodo(t.id, { is_cancelled: false }),
      () => saveTodo(t.id, { is_cancelled: true }));
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
      return [...done, ...(e ? [{ label: "Open logged entry", run: () => openEntry(e, m.day) }] : []), edit, remove];
    }
    const moves: Item[] = meeting
      ? []
      : [
          { label: "‹ Move to the day before", run: () => move(s, -1) },
          { label: "Move to the day after ›", run: () => move(s, 1) },
        ];
    return [
      ...(t.is_tentative ? [tentativeItem] : []),
      { label: "✓ Log time", run: () => openLog(t, s, m.day) },
      ...(t.is_tentative ? [] : [tentativeItem]),
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

  // Ctrl/Cmd+Z undoes, unless you are typing or a form is open.
  function keys(ev: KeyboardEvent) {
    if (menu) return menuKeys(ev);
    if (!(ev.ctrlKey || ev.metaKey) || ev.shiftKey || ev.key.toLowerCase() !== "z" || panel) return;
    const el = document.activeElement as HTMLElement | null;
    if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
    ev.preventDefault();
    undoLast();
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
    | { kind: "email" }
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
    markDone = t.kind === "meeting" || slotsOf(t).filter((s) => !s.entry_id && !s.is_cancelled).length <= 1;
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
    const categoryId = t.category_id ?? (catById.has(saved) ? saved : tax?.categories[0]?.id ?? "");
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
    const categoryId = catById.has(saved) ? saved : tax?.categories[0]?.id ?? "";
    return { date: day, start: s, end: e, categoryId };
  }

  async function entrySaved(p: Extract<Panel, { kind: "entry" }>, f: TimeEntryFields, id: string,
                            action: "created" | "updated" | "copied" | "deleted") {
    try { localStorage.setItem(LAST_CATEGORY, f.category_id); } catch {}
    const old = p.entry ? ({ ...$state.snapshot(p.entry) } as TimeEntry) : null;
    const when = `${dayName(f.started_at.slice(0, 10))} ${dayNum(f.started_at.slice(0, 10))}`;
    if (action === "created") remember(`Logged ${label(f) || "time"} on ${when}`, () => deleteEntry(id));
    else if (action === "copied") remember(`Copied the entry to ${when}`, () => deleteEntry(id));
    else if (action === "deleted" && old) remember(`Deleted the entry on ${when}`, () => reinsertEntry(old));
    else if (action === "updated" && old) {
      const { id: _id, minutes: _m, ...fields } = old;
      remember(`Changed the entry on ${when}`, () => saveEntry(old.id, fields));
    }
    panel = null;
    await load();
  }

  async function logged(p: Extract<Panel, { kind: "log" }>, f: TimeEntryFields, entryId: string) {
    const slotBefore = p.slot ? snapSlot(p.slot) : null;
    const doneBefore = { is_done: p.todo.is_done, done_at: p.todo.done_at };
    const markedDone = markDone && !p.todo.is_done;
    let newSlot = "";
    try {
      const day = f.started_at.slice(0, 10);
      if (p.slot) await saveSlot(p.slot.id, { entry_id: entryId, planned_on: day });
      else newSlot = await saveSlot(null, { todo_id: p.todo.id, planned_on: day, entry_id: entryId });
      if (markedDone) await saveTodo(p.todo.id, { is_done: true, done_at: new Date().toISOString() });
      try { localStorage.setItem(LAST_CATEGORY, f.category_id); } catch {}
      remember(`Logged ${q(p.todo)}`, async () => {
        if (slotBefore) await saveSlot(slotBefore.id, { entry_id: null, planned_on: slotBefore.planned_on });
        else if (newSlot) await deleteSlot(newSlot);
        await deleteEntry(entryId);
        if (markedDone) await saveTodo(p.todo.id, doneBefore);
      });
    } catch (e) {
      error = (e as Error).message;
    }
    panel = null;
    await load();
  }

  async function closed(info: { action: "created" | "updated" | "deleted" | "cancelled" | "restored"; ids?: string[] }) {
    const p = panel;
    const t = p && p.kind === "todo" && p.todo ? snapTodo(p.todo) : null;
    const own = t ? slots.filter((s) => s.todo_id === t.id).map(snapSlot) : [];
    if (info.action === "created" && info.ids?.length) {
      const ids = info.ids;
      remember(ids.length > 1 ? `Added ${ids.length} meetings` : "Added a to-do",
        async () => { for (const id of ids) await deleteTodo(id); });
    } else if (t && info.action === "deleted") {
      remember(`Deleted ${q(t)}`, () => reinsertTodo(t, own));
    } else if (t && (info.action === "cancelled" || info.action === "restored")) {
      remember(`${info.action === "cancelled" ? "Cancelled" : "Restored"} ${q(t)}`,
        () => saveTodo(t.id, { is_cancelled: t.is_cancelled }));
    } else if (t && info.action === "updated") {
      const { id: _id, ...fields } = t;
      remember(`Edited ${q(t)}`, async () => {
        await saveTodo(t.id, fields);
        for (const s of own) {
          await saveSlot(s.id, { planned_on: s.planned_on, start_time: s.start_time, end_time: s.end_time, planned_hours: s.planned_hours });
        }
      });
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
    const before = slotsOf(t).filter((x) => x.planned_on >= start && x.planned_on <= end).map(snapSlot);
    const estBefore = t.est_hours;
    const created: string[] = [];
    const removed: Slot[] = [];
    try {
      for (const d of days) {
        const here = before.filter((x) => x.planned_on === d && !x.is_cancelled);
        if (spreadPick[d]) {
          if (here.length) {
            for (const x of here) await saveSlot(x.id, { planned_hours: perDay });
          } else {
            created.push(await saveSlot(null, { todo_id: t.id, planned_on: d, planned_hours: perDay }));
          }
        } else {
          for (const x of here.filter((x) => !x.entry_id)) {
            await deleteSlot(x.id);
            removed.push(x);
          }
        }
      }
      if (spreadHours !== estBefore) await saveTodo(t.id, { est_hours: spreadHours });
      remember(`Planned ${q(t)} over ${spreadDays.length} ${spreadDays.length === 1 ? "day" : "days"}`, async () => {
        for (const id of created) await deleteSlot(id);
        for (const x of removed) await reinsertSlot(x);
        for (const x of before.filter((b) => !removed.some((r) => r.id === b.id))) {
          await saveSlot(x.id, { planned_hours: x.planned_hours });
        }
        await saveTodo(t.id, { est_hours: estBefore });
      });
    } catch (e) {
      error = (e as Error).message;
    }
    panel = null;
    await load();
  }

  // ---- to-dos from milestones live this week ------------------------------------------------
  // Each milestone whose dates touch the week (or which is overdue) is offered
  // with this week's share of its remaining hours; ticked ones become to-dos
  // linked to the milestone, its project and category.
  type MsRow = { p: Project; m: Milestone; info: MilestoneWeek; already: boolean; pick: boolean; hours: number | null; must: boolean };
  let msRows = $state<MsRow[]>([]);
  let msLoading = $state(false);

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
          const already = todos.some((t) => t.milestone_id === m.id && t.kind === "task" && !t.is_cancelled);
          const urgent = info.overdue || info.dueThisWeek;
          rows.push({ p, m, info, already, pick: !already && urgent, hours: info.suggested, must: m.hard_deadline || urgent });
        }
      }
      // overdue first, then by due date; undated last
      msRows = rows.sort((a, b) =>
        Number(b.info.overdue) - Number(a.info.overdue) || (a.info.due ?? "9").localeCompare(b.info.due ?? "9"));
    } catch (e) {
      error = (e as Error).message;
    } finally {
      msLoading = false;
    }
  }

  async function addFromMilestones() {
    const picked = msRows.filter((r) => r.pick && !r.already);
    const added: string[] = [];
    try {
      for (const r of picked) {
        added.push(await saveTodo(null, {
          kind: "task", title: r.m.title, due_on: isCurrent ? today() : start,
          category_id: r.p.category_id, project_id: r.p.id, milestone_id: r.m.id,
          est_hours: r.hours, must_this_week: r.must,
        }));
      }
      if (added.length) {
        remember(`Added ${added.length} to-${added.length === 1 ? "do" : "dos"} from milestones`,
          async () => { for (const id of added) await deleteTodo(id); });
      }
    } catch (e) {
      error = (e as Error).message;
    }
    panel = null;
    await load();
  }

  // ---- email checks: one to-do per weekday ------------------------------------------------
  const EMAIL_TITLE = "Email check";
  const weekdays = $derived(days.filter((d) => { const w = parse(d).getDay(); return w >= 1 && w <= 5; }));
  let emailPick = $state<Record<string, boolean>>({});
  let emailHours = $state(1.5);
  let emailCategory = $state("");

  function hasEmailCheck(d: string): boolean {
    return weekSlots.some((x) => x.planned_on === d && !x.is_cancelled &&
      todoById.get(x.todo_id)?.title.trim().toLowerCase() === EMAIL_TITLE.toLowerCase());
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
    const added: string[] = [];
    try {
      for (const d of picked) {
        const id = await saveTodo(null, {
          kind: "task", title: EMAIL_TITLE, due_on: d, category_id: emailCategory || null,
          est_hours: emailHours, must_this_week: false,
        });
        added.push(id);
        await saveSlot(null, { todo_id: id, planned_on: d, planned_hours: null });
      }
      if (added.length) {
        remember(`Added ${added.length} email ${added.length === 1 ? "check" : "checks"}`,
          async () => { for (const id of added) await deleteTodo(id); });
      }
    } catch (e) {
      error = (e as Error).message;
    }
    panel = null;
    await load();
  }

  /** Hours planned for this card: its own share, or the to-do's estimate when it has just one day. */
  function cardHours(s: Slot, t: Todo): number | null {
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
    const added: string[] = [];
    try {
      for (const m of picked) {
        const [sh, sm] = m.start.split(":").map(Number);
        const [eh, em] = m.end.split(":").map(Number);
        const len = Math.round(((eh * 60 + em - sh * 60 - sm) / 60) * 100) / 100;
        const id = await saveTodo(null, {
          kind: "meeting", title: m.title, due_on: m.date, category_id: importCategory || null,
          est_hours: len, must_this_week: true, note: m.location || null,
        });
        added.push(id);
        await saveSlot(null, { todo_id: id, planned_on: m.date, start_time: m.start, end_time: m.end, planned_hours: len });
      }
      importNote = `Added ${picked.length} ${picked.length === 1 ? "meeting" : "meetings"}.`;
      remember(`Imported ${added.length} ${added.length === 1 ? "meeting" : "meetings"}`,
        async () => { for (const id of added) await deleteTodo(id); });
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
    <button onclick={undoLast} disabled={!history.length}
            title={history.length ? `Undo: ${history[history.length - 1].label} (Ctrl+Z)` : "Nothing to undo"}>↶ Undo</button>
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
      <div class="day" class:today={d === today()} class:past={d < today()}>
        <div class="day-head">
          <span class="dname">{dayName(d)} <span class="dnum">{dayNum(d)}</span></span>
          {#if loggedOn(d)}<span class="muted small">{fmtHours(loggedOn(d))} logged</span>{/if}
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
              {#if s.is_cancelled}<span class="off">cancelled</span>{:else if s.entry_id}<span class="ok">✓ {e ? fmtHours(e.minutes / 60) : "logged"}</span>{:else if pending(t)}<span class="off">from Outlook — to review</span>{:else if tentative(t)}<span class="off">tentative</span>{:else if t.is_done}<span class="ok">done</span>{/if}
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
      <div class="group" class:muted-group={g.key === "done"}>
        <h3>{g.title} <span class="muted small">{g.rows.length}</span></h3>
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
                  {#if carried.has(t.id)} · <span class="carried">from week of {fmtDay(weekStart(t.due_on))}</span>{/if}
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
    {#if toast.canUndo}<button onclick={undoLast}>Undo</button>{/if}
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
          <ul class="ms-pick">
            {#each msRows as r (r.m.id)}
              <li class:off={r.already}>
                <input type="checkbox" bind:checked={r.pick} disabled={r.already} aria-label={`Add ${r.m.title}`} />
                <div class="ms-what">
                  <strong>{r.m.title}</strong>
                  <span class="muted">{r.p.name}</span>
                  <span class="ms-when" class:late={r.info.overdue}>
                    {#if r.info.overdue}overdue since {fmtDay(r.info.due!)}
                    {:else if r.info.due}due {fmtDay(r.info.due)}{r.m.due_on ? "" : " (project end)"}
                    {:else}no due date{/if}
                    {#if r.m.hard_deadline} · hard deadline{/if}
                    {#if r.info.remaining !== null} · {fmtHours(r.info.remaining)} left{:else} · no planned hours{/if}
                    {#if r.already} · already a to-do this week{/if}
                  </span>
                </div>
                {#if !r.already}
                  <label class="ms-h">h <input type="number" min="0" step="0.5" bind:value={r.hours} aria-label="Hours this week" /></label>
                  <label class="ms-must"><input type="checkbox" bind:checked={r.must} /> must</label>
                {/if}
              </li>
            {/each}
          </ul>
        {/if}
        <div class="pick-actions">
          {#if msRows.some((r) => r.pick && !r.already)}
            {@const n = msRows.filter((r) => r.pick && !r.already).length}
            <button class="primary" onclick={addFromMilestones}>Add {n} to-{n === 1 ? "do" : "dos"}</button>
          {:else}
            <button class="primary" disabled>Tick milestones to add</button>
          {/if}
          <button onclick={() => (panel = null)}>Cancel</button>
        </div>
      </div>
    {:else if panel.kind === "outlook"}
      <h2>Outlook calendar</h2>
      <OutlookSettings oncancel={() => (panel = null)}
                       onsaved={async (changed) => { panel = null; feed = await loadFeed(); if (changed && feed?.ics_url) runSync(); }} />
    {:else if panel.kind === "email"}
      <h2>Create email checks</h2>
      <div class="pick">
        <p class="muted small">
          One “{EMAIL_TITLE}” to-do on each ticked day; edit any day's afterwards from its card. Email time counts in
          equal shares to Teaching, Admin and Outreach, whichever Email category it is logged under.
        </p>
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
            <button class="primary" onclick={createEmailChecks}>Create {n} email {n === 1 ? "check" : "checks"}</button>
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
  .ms-pick { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.3rem; max-height: 55vh; overflow-y: auto; }
  .ms-pick li { display: grid; grid-template-columns: auto 1fr auto auto; gap: 0.6rem; align-items: center; padding: 0.4rem 0.3rem; border-bottom: 1px solid var(--rule); }
  .ms-pick li.off { opacity: 0.55; }
  .ms-pick input[type="checkbox"] { width: auto; }
  .ms-what { display: flex; flex-wrap: wrap; gap: 0.15rem 0.5rem; align-items: baseline; font-size: 0.88rem; }
  .ms-when { width: 100%; font-size: 0.78rem; color: var(--ink-soft); }
  .ms-when.late { color: var(--danger); }
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
  .carried { color: var(--accent); }
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
