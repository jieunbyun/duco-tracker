<script lang="ts">
  import {
    loadTaxonomy, loadProjects, loadWeekPlan, loadUnfinishedBefore, loadEntriesBetween, loggedHoursOf, saveSlot, deleteSlot, saveTodo, deleteTodo, fmtHours,
    saveEntry, deleteEntry, loadAllHours, targetOn, loadIdeas, openSlotOn, loadIdeaNotes, addIdeaNote, saveIdeaNote, deleteIdeaNote,
    setMilestoneStatus, byPlanningOrder,
  } from "../lib/data";
  import type { Taxonomy, Project, Milestone, Todo, Slot, TimeEntry, TimeEntryFields, IdeaNote } from "../lib/data";
  import { milestoneWeek } from "../lib/plan";
  import { shareRemaining } from "../lib/share";
  import type { MilestoneWeek } from "../lib/plan";
  import { addDays, today, weekStart, parse, fmtDay, daysIn } from "../lib/dates";
  import { meetingsInRange } from "../lib/ics";
  import type { Meeting } from "../lib/ics";
  import EntryForm from "../lib/EntryForm.svelte";
  import TodoForm from "../lib/TodoForm.svelte";
  import Linked from "../lib/Linked.svelte";
  import CvForm from "../lib/CvForm.svelte";
  import CvRelated from "../lib/CvRelated.svelte";
  import OutlookInbox from "../lib/OutlookInbox.svelte";
  import OutlookSettings from "../lib/OutlookSettings.svelte";
  import Sortable from "../lib/Sortable.svelte";
  import { loadFeed, syncOutlook, isStale, loadUnreviewed, dismissOutlook } from "../lib/outlook";
  import type { Feed } from "../lib/outlook";
  import { undoable, nameLast, undoLast, quietly } from "../lib/undo.svelte";
  import {
    loadTidies, addTidy, saveTidy, deleteTidy, cleanLink, addFollowOn, loadLinked, moveWithFollowOns, unlinkFollowOns, noFollows,
  } from "../lib/tidy";
  import { agendasFor } from "../lib/meetings";
  import BackLink from "../lib/BackLink.svelte";
  import { tick } from "svelte";
  import type { Tidy } from "../lib/tidy";
  import { loadRepeats, startRepeat, stopRepeat, fillRepeats, nextDates, describe as describeRepeat, waysFrom, fmtShort } from "../lib/repeat";
  import type { Repeat, Every } from "../lib/repeat";

  const SHOW_LOGGED = "week.showLogged";
  const MS_PICKS = "week.msPicks"; // + From milestones as you last left it (this browser)
  const LAST_CATEGORY = "log.category";

  // ---- week ------------------------------------------------------------------
  let offset = $state(0);
  const start = $derived(addDays(weekStart(today()), 7 * offset));
  const end = $derived(addDays(start, 6));
  const days = $derived(Array.from({ length: 7 }, (_, i) => addDays(start, i)));
  const isCurrent = $derived(offset === 0);

  // ---- on a phone: the calendar or the to-dos, and the calendar one day at a time ----
  const MOBILE_VIEW = "week.mobileView"; // which of the two you last looked at (this browser)
  const phoneQuery = window.matchMedia("(max-width: 48rem)");
  let phone = $state(phoneQuery.matches);
  $effect(() => {
    const on = () => (phone = phoneQuery.matches);
    phoneQuery.addEventListener("change", on);
    return () => phoneQuery.removeEventListener("change", on);
  });
  let mobileView = $state<"calendar" | "todos">((() => {
    try { return localStorage.getItem(MOBILE_VIEW) === "todos" ? "todos" : "calendar"; } catch { return "calendar"; }
  })());
  function showView(v: "calendar" | "todos") {
    mobileView = v;
    try { localStorage.setItem(MOBILE_VIEW, v); } catch {}
  }
  let pickedDay = $state<string | null>(null);
  // the day picked in this week; else today, if it is in this week; else its first day
  const phoneDay = $derived(pickedDay && days.includes(pickedDay) ? pickedDay : days.includes(today()) ? today() : start);
  const shownDays = $derived(phone ? [phoneDay] : days);
  // back from Planning (#/week?w=<week>&ms=1): that week, with + From milestones open again;
  // back from the Logbook (#/week?w=<week>): that week
  const arrivedWith = new URLSearchParams(location.hash.split("?")[1] ?? "");
  let reopenMs = !!arrivedWith.get("ms");
  // from Meetings (#/week?w=<week>&show=<to-do>&agenda=<meeting>): that meeting picked out, and Back to its agenda
  let showTodo = arrivedWith.get("show");
  const agendaBack = /^[\w-]+$/.test(arrivedWith.get("agenda") ?? "") ? `#/meetings?m=${arrivedWith.get("agenda")}` : null;
  let lit = $state<string | null>(null);
  // from the Day tab (#/week?w=<week>&d=<day>&entry=…, todo=…, tidy=… or idea=…&note=…): that
  // day, and the entry open to change (a small task lit up)
  const ID = /^[\w-]+$/;
  let fromDay = arrivedWith.get("d") && /^\d{4}-\d\d-\d\d$/.test(arrivedWith.get("d")!)
    ? { day: arrivedWith.get("d")!, ...Object.fromEntries(["entry", "todo", "tidy", "idea", "note"]
        .map((k) => [k, ID.test(arrivedWith.get(k) ?? "") ? arrivedWith.get(k)! : null])) } as
        { day: string; entry: string | null; todo: string | null; tidy: string | null; idea: string | null; note: string | null }
    : null;
  if (fromDay) pickedDay = fromDay.day;
  if (arrivedWith.get("w")) {
    history.replaceState(null, "", "#/week");
    offset = Math.round((daysIn({ from: weekStart(today()), to: weekStart(arrivedWith.get("w")!) }) - 1) / 7);
  }

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
      const [tFrom, tTo] = monthView ? [gridFrom, gridTo] : [from, to];
      const [plan, logged, p, review, thoughts, thoughtNotes, tidyUps, series] = await Promise.all([
        loadWeekPlan(from, to), loadEntriesBetween(from, to), loadProjects(), loadUnreviewed(), loadIdeas(), loadIdeaNotes(),
        // small tasks must never keep the week from opening; the month view takes the month's
        loadTidies(tFrom, tTo).catch(() => null),
        loadRepeats().catch(() => null),
      ]);
      if (id !== request) return;
      // the repeating ones due on these days and not made yet: made now, quietly (not an undo of yours)
      let small = tidyUps;
      if (small && series?.length) {
        const made = await quietly(() => fillRepeats(series, tFrom, tTo, small!)).catch(() => 0);
        if (made) small = await loadTidies(tFrom, tTo).catch(() => small);
        if (id !== request) return;
      }
      repeats = series;
      tidyMissing = small === null;
      tidies = (small ?? []).filter((t) => !t.skipped); // one deleted from its series stays hidden
      // the follow-ons of these, and what they follow on from, in other weeks (none until 0072 is run)
      const linked = await loadLinked(tidies).catch(() => [] as Tidy[]);
      if (id !== request) return;
      tidyLinked = linked.filter((t) => !t.skipped);
      projects = p;
      inbox = review;
      ideas = thoughts;
      ideaNotes = thoughtNotes;
      todos = plan.todos;
      slots = plan.slots;
      // which calendar meetings have an agenda in Meetings (none until 0064 is run)
      agendaOf = await agendasFor(plan.todos.filter((t) => t.kind === "meeting").map((t) => t.id)).catch(() => new Map());
      if (id !== request) return;
      entries = logged;
      error = "";
      if (showTodo) {
        const t = showTodo;
        showTodo = null;
        lit = t;
        tick().then(() => document.querySelector(`[data-todo="${t}"]`)?.scrollIntoView({ block: "center" }));
        setTimeout(() => (lit = null), 2500);
      }
      if (reopenMs) {
        reopenMs = false;
        openMilestones();
      }
      if (fromDay) arriveFromDay(fromDay);
      if (showTidy) lightTidy(showTidy);
    } catch (e) {
      if (id === request) error = (e as Error).message;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    void start;
    void monthView;
    void monthFirst;
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
  // meetings by their time; to-dos in the order you have dragged them into (one
  // not yet placed in it, say just planned there, goes at the end)
  function slotsOn(day: string, kind: "task" | "meeting"): Slot[] {
    const placed = (s: Slot) => (kind === "task" ? s.sort_order ?? Infinity : 0);
    return weekSlots
      .filter((s) => s.planned_on === day && todoById.get(s.todo_id)?.kind === kind)
      .sort((a, b) => placed(a) - placed(b) ||
        (a.start_time ?? "").localeCompare(b.start_time ?? "") || (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id.localeCompare(b.id));
  }

  // ---- rearranging a day's to-dos: drag a card's ⠿ handle (mouse or touch), or arrow keys on it ----
  let dayDrag = $state<{ day: string; id: string; from: string[]; order: string[] } | null>(null);
  function dutiesOn(day: string): Slot[] {
    const list = slotsOn(day, "task");
    if (dayDrag?.day !== day) return list;
    return dayDrag.order.map((id) => list.find((s) => s.id === id)).filter((s): s is Slot => !!s);
  }
  // as with ideas, the window follows the pointer for the whole drag
  function startCardDrag(ev: PointerEvent, s: Slot) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    const order = slotsOn(s.planned_on, "task").map((x) => x.id);
    dayDrag = { day: s.planned_on, id: s.id, from: order, order };
    window.addEventListener("pointermove", cardDragMove);
    window.addEventListener("pointerup", endCardDrag);
    window.addEventListener("pointercancel", endCardDrag);
  }
  function cardDragMove(ev: PointerEvent) {
    if (!dayDrag) return;
    const over = (document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null)?.closest<HTMLElement>(".card.duty");
    const overId = over?.dataset.id;
    if (!overId || overId === dayDrag.id || over!.dataset.day !== dayDrag.day) return;
    const order = dayDrag.order.filter((id) => id !== dayDrag!.id);
    const r = over!.getBoundingClientRect();
    order.splice(order.indexOf(overId) + (ev.clientY > r.top + r.height / 2 ? 1 : 0), 0, dayDrag.id);
    if (order.join() !== dayDrag.order.join()) dayDrag.order = order;
  }
  async function endCardDrag() {
    window.removeEventListener("pointermove", cardDragMove);
    window.removeEventListener("pointerup", endCardDrag);
    window.removeEventListener("pointercancel", endCardDrag);
    if (!dayDrag) return;
    const { day, from, order } = dayDrag;
    dayDrag = null;
    if (order.join() !== from.join()) await saveDayOrder(day, order);
  }
  function cardKeyMove(ev: KeyboardEvent, s: Slot) {
    if (ev.key !== "ArrowUp" && ev.key !== "ArrowDown") return;
    ev.preventDefault();
    const order = slotsOn(s.planned_on, "task").map((x) => x.id);
    const i = order.indexOf(s.id);
    const j = i + (ev.key === "ArrowUp" ? -1 : 1);
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    saveDayOrder(s.planned_on, order).then(() => {
      // keep the focus on the moved card's handle
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`.card.duty[data-id="${s.id}"] .grip`)?.focus());
    });
  }
  /** Store a day's order as sort_order 10, 20, 30…, changing only what moved. */
  async function saveDayOrder(day: string, order: string[]) {
    const changes = order
      .map((id, i) => ({ id, sort_order: (i + 1) * 10 }))
      .filter((c) => slots.find((s) => s.id === c.id)?.sort_order !== c.sort_order);
    if (!changes.length) return;
    // show the new order at once; the reload confirms it
    const at = new Map(changes.map((c) => [c.id, c.sort_order]));
    slots = slots.map((s) => (at.has(s.id) ? { ...s, sort_order: at.get(s.id)! } : s));
    await change(`Reordered the to-dos on ${dayName(day)} ${dayNum(day)}`,
      async () => { for (const c of changes) await saveSlot(c.id, { sort_order: c.sort_order }); });
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
    // how far through the week's work: what is logged on the plan, against that plus what
    // is still to do — the cards not yet logged (a to-do's card holds what is left of it)
    // and the must-dos' hours left. Logged cards count once, by what was logged, not as
    // planned. Time logged on nothing planned (no card) is not part of the plan's progress.
    const onPlan = new Set(slots.filter((s) => s.entry_id && !uncounted(todoById.get(s.todo_id))).map((s) => s.entry_id));
    const loggedPlanned = entries.reduce((sum, e) => sum + (onPlan.has(e.id) ? e.minutes / 60 : 0), 0);
    const unplanned = logged - loggedPlanned;
    let toDo = must.hours;
    for (const s of weekSlots) {
      if (s.entry_id || s.is_cancelled) continue;
      const t = todoById.get(s.todo_id);
      if (!t || uncounted(t) || t.is_done) continue;
      toDo += (t.kind === "meeting" ? s.planned_hours : cardHours(s, t)) ?? 0;
    }
    const plan = loggedPlanned + toDo;
    const target = (tax?.areas ?? []).reduce((sum, a) => {
      const t = targetOn(tax!.targets, a.id, start);
      return sum + (t ? t.weekly_hours + t.email_weekly_hours : 0);
    }, 0);
    return { planned, calendar, must, flex, unknown, logged, loggedPlanned, unplanned, plan, target };
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
  // A logged day is behind it: a to-do whose days this week are all logged stays on the list
  // (with its days ✓) until it is ticked done.
  const onCalendar = $derived(new Set(weekSlots.filter((s) => !s.is_cancelled && !s.entry_id).map((s) => s.todo_id)));
  const loggedThisWeek = $derived(new Set(weekSlots.filter((s) => !s.is_cancelled && s.entry_id).map((s) => s.todo_id)));
  // Cancelled to-dos stay in their group, struck through, until restored or deleted.
  const unplaced = $derived(tasks.filter((t) =>
    !onCalendar.has(t.id) && !pending(t) && !(t.is_done && !t.is_cancelled && loggedThisWeek.has(t.id))));
  const groups = $derived([
    { key: "must", title: "Must do", rows: unplaced.filter((t) => (!t.is_done || t.is_cancelled) && t.must_this_week) },
    { key: "flex", title: "Flexible", rows: unplaced.filter((t) => (!t.is_done || t.is_cancelled) && !t.must_this_week) },
    { key: "done", title: "Done", rows: unplaced.filter((t) => t.is_done && !t.is_cancelled) },
  ].map((g) => ({ ...g, rows: [...g.rows].sort((a, b) => a.sort_order - b.sort_order || a.title.localeCompare(b.title)) })));

  let todoOrderSaving = $state(false);
  async function saveTodoOrder(title: string, order: string[]) {
    if (todoOrderSaving) return;
    const changes = order
      .map((id, i) => ({ id, sort_order: (i + 1) * 10 }))
      .filter((c) => todoById.get(c.id)?.sort_order !== c.sort_order);
    if (!changes.length) return;
    todoOrderSaving = true;
    const at = new Map(changes.map((c) => [c.id, c.sort_order]));
    todos = todos.map((t) => (at.has(t.id) ? { ...t, sort_order: at.get(t.id)! } : t));
    try {
      await change(`Reordered the ${title.toLowerCase()} to-dos`,
        async () => { for (const c of changes) await saveTodo(c.id, { sort_order: c.sort_order }); });
    } finally {
      todoOrderSaving = false;
    }
  }

  function slotsOf(t: Todo): Slot[] {
    return slots.filter((s) => s.todo_id === t.id).sort((a, b) => a.planned_on.localeCompare(b.planned_on));
  }
  function loggedFor(t: Todo): number {
    return slotsOf(t).reduce((s, x) => s + ((x.entry_id && entryById.get(x.entry_id)?.minutes) || 0) / 60, 0);
  }
  /** A to-do's hours still to go: its estimate (without one, its days' planned hours) less
   *  all that is logged on it; below zero when it has run over. Null with no figure to go by. */
  function leftFor(t: Todo): number | null {
    let plan = t.est_hours;
    if (plan === null) {
      const hs = slotsOf(t).filter((x) => !x.is_cancelled).map((x) => x.planned_hours);
      if (!hs.length || hs.some((h) => h === null)) return null;
      plan = hs.reduce((a: number, b) => a + b!, 0);
    }
    return plan - loggedFor(t);
  }
  const leftText = (h: number) => (h < 0 ? `${fmtHours(-h)} over` : `${fmtHours(h)} left`);

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
          await saveSlot(s.id, { planned_on: to, sort_order: null });
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
  /**
   * A to-do on a milestone stands for it: done marks the milestone done as well, and
   * reopening reopens a milestone that is done. (Undo takes back both as one.)
   */
  function milestoneFollows(t: Todo, done: boolean): string | null {
    if (t.kind !== "task" || !t.milestone_id) return null;
    const m = projects.flatMap((p) => p.milestone).find((x) => x.id === t.milestone_id);
    if (!m) return done ? t.milestone_id : null; // not loaded here: done is still safe to set
    return (done ? m.status !== "done" : m.status === "done") ? m.id : null;
  }
  function setDone(t: Todo, done: boolean) {
    const ms = milestoneFollows(t, done);
    const also = ms ? " and its milestone" : "";
    return change(done ? `Marked ${q(t)}${also} done` : `Reopened ${q(t)}${also}`, async () => {
      await saveTodo(t.id, { is_done: done, done_at: done ? new Date().toISOString() : null });
      if (ms) await setMilestoneStatus(ms, done ? "done" : "active");
    });
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

  // ---- a meeting's agenda, kept in Meetings: there and back ------------------------------------
  let agendaOf = $state(new Map<string, string>()); // calendar meeting (to-do) → its meeting in Meetings
  function toAgenda(t: Todo, day: string) {
    const here = `#/week?w=${start}`;
    const back = encodeURIComponent(`${here}&show=${t.id}`);
    history.replaceState(null, "", here); // so the browser's Back lands here too
    const m = agendaOf.get(t.id);
    location.hash = m ? `#/meetings?m=${m}&back=${back}`
      : `#/meetings?new=1&todo=${t.id}&date=${day}&title=${encodeURIComponent(t.title)}&back=${back}`;
  }
  function agendaItem(t: Todo, day: string): Item[] {
    return [{ label: agendaOf.has(t.id) ? "📋 Open agenda ›" : "📋 + Agenda…", run: () => toAgenda(t, day) }];
  }

  // ---- small tasks / deadlines: a checkbox and a few words on a day, no hours, under each day ----
  // A checkbox and a few words; moved like a to-do's card (the day before, the day after, or
  // any date), renamed or deleted from its menu. Never counted as planned or logged time.
  let tidies = $state<Tidy[]>([]);
  let tidyLinked = $state<Tidy[]>([]); // follow-ons (and what they follow) not among these days
  let tidyMissing = $state(false); // until 0058 is run
  let repeats = $state<Repeat[] | null>(null); // repeating small tasks; null until 0071 is run
  const repeatOf = (t: Tidy) => (t.repeat_id ? repeats?.find((r) => r.id === t.repeat_id) : undefined);
  let tidyDraft = $state<Record<string, string>>({});
  let tidyEdit = $state<{ id: string; title: string } | null>(null);
  let tidyMenu = $state<{ t: Tidy; x: number; y: number } | null>(null);
  // a day's small tasks in the order you have dragged them into (new ones at the end)
  const tidyOrder = (a: Tidy, b: Tidy) =>
    (a.sort_order ?? Infinity) - (b.sort_order ?? Infinity) || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id);
  function tidiesOn(day: string): Tidy[] {
    const list = tidies.filter((x) => x.day === day).sort(tidyOrder);
    if (tidyDrag?.day !== day) return list;
    return tidyDrag.order.map((id) => list.find((t) => t.id === id)).filter((t): t is Tidy => !!t);
  }

  // ---- rearranging a day's small tasks: drag the ⠿ handle (mouse or touch), or arrow keys on it ----
  let tidyDrag = $state<{ day: string; id: string; from: string[]; order: string[] } | null>(null);
  function startTidyDrag(ev: PointerEvent, t: Tidy) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    const order = tidies.filter((x) => x.day === t.day).sort(tidyOrder).map((x) => x.id);
    tidyDrag = { day: t.day, id: t.id, from: order, order };
    window.addEventListener("pointermove", tidyDragMove);
    window.addEventListener("pointerup", endTidyDrag);
    window.addEventListener("pointercancel", endTidyDrag);
  }
  function tidyDragMove(ev: PointerEvent) {
    if (!tidyDrag) return;
    const over = (document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null)?.closest<HTMLElement>(".tidy-row");
    const overId = over?.dataset.id;
    if (!overId || overId === tidyDrag.id || over!.dataset.day !== tidyDrag.day) return;
    const order = tidyDrag.order.filter((id) => id !== tidyDrag!.id);
    const r = over!.getBoundingClientRect();
    order.splice(order.indexOf(overId) + (ev.clientY > r.top + r.height / 2 ? 1 : 0), 0, tidyDrag.id);
    if (order.join() !== tidyDrag.order.join()) tidyDrag.order = order;
  }
  async function endTidyDrag() {
    window.removeEventListener("pointermove", tidyDragMove);
    window.removeEventListener("pointerup", endTidyDrag);
    window.removeEventListener("pointercancel", endTidyDrag);
    if (!tidyDrag) return;
    const { day, from, order } = tidyDrag;
    tidyDrag = null;
    if (order.join() !== from.join()) await saveTidyOrder(day, order);
  }
  function tidyKeyMove(ev: KeyboardEvent, t: Tidy) {
    if (ev.key !== "ArrowUp" && ev.key !== "ArrowDown") return;
    ev.preventDefault();
    const order = tidies.filter((x) => x.day === t.day).sort(tidyOrder).map((x) => x.id);
    const i = order.indexOf(t.id);
    const j = i + (ev.key === "ArrowUp" ? -1 : 1);
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    saveTidyOrder(t.day, order).then(() =>
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`.tidy-row[data-id="${t.id}"] .tgrip`)?.focus()));
  }
  /** Store a day's order as sort_order 10, 20, 30…, changing only what moved. */
  async function saveTidyOrder(day: string, order: string[]) {
    const changes = order.map((id, i) => ({ id, sort_order: (i + 1) * 10 }))
      .filter((c) => tidies.find((t) => t.id === c.id)?.sort_order !== c.sort_order);
    if (!changes.length) return;
    const at = new Map(changes.map((c) => [c.id, c.sort_order]));
    tidies = tidies.map((t) => (at.has(t.id) ? { ...t, sort_order: at.get(t.id)! } : t)); // at once; the reload confirms it
    await change(`Reordered the small tasks on ${dayName(day)} ${dayNum(day)}`,
      async () => { for (const c of changes) await saveTidy(c.id, { sort_order: c.sort_order }); });
  }

  // a tidy-up: ticked so in the menu, and coloured
  async function setTidyUp(t: Tidy, on: boolean) {
    const ok = await change(on ? `Marked ${q(t)} a tidy-up` : `${q(t)} no longer a tidy-up`, () => saveTidy(t.id, { is_tidy: on }));
    if (!ok && /is_tidy/i.test(error)) error = "Marking tidy-ups needs web/db/0066_tidy_kind.sql run first, in the Supabase SQL editor.";
  }

  // the month view: only the small tasks / deadlines, a month at a time (remembered in this browser)
  const MONTH_VIEW = "week.monthView";
  let monthView = $state(!fromDay && (() => { try { return localStorage.getItem(MONTH_VIEW) === "1"; } catch { return false; } })());
  let monthAt = $state(""); // the first day of the month shown ("" until one is picked)
  const shiftMonth = (m: string, n: number) => {
    const d = parse(m);
    d.setMonth(d.getMonth() + n, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
  };
  const thisMonth = $derived(`${today().slice(0, 7)}-01`);
  const monthFirst = $derived(monthAt || `${(isCurrent ? today() : start).slice(0, 7)}-01`);
  const monthLast = $derived(addDays(shiftMonth(monthFirst, 1), -1));
  const gridFrom = $derived(weekStart(monthFirst));
  const gridTo = $derived(addDays(weekStart(monthLast), 6));
  const span = (a: string, b: string) => { const out: string[] = []; for (let d = a; d <= b; d = addDays(d, 1)) out.push(d); return out; };
  const gridDays = $derived(span(gridFrom, gridTo));
  const monthDays = $derived(span(monthFirst, monthLast));
  const monthLabel = $derived(parse(monthFirst).toLocaleDateString("en-GB", { month: "long", year: "numeric" }));
  function setMonthView(on: boolean) {
    monthView = on;
    if (on) monthAt = `${(isCurrent ? today() : start).slice(0, 7)}-01`;
    try { localStorage.setItem(MONTH_VIEW, on ? "1" : "0"); } catch {}
  }
  // on a phone the month is a list of its days: open it at today
  function toToday(node: HTMLElement) {
    requestAnimationFrame(() => node.querySelector<HTMLElement>(".m-cell.today")?.scrollIntoView({ block: "start" }));
  }

  async function addTidyOn(day: string) {
    const title = (tidyDraft[day] ?? "").trim();
    if (!title) return;
    tidyDraft[day] = "";
    const order = Math.max(0, ...tidiesOn(day).map((x) => x.sort_order ?? 0)) + 10;
    await change(`Added small task ${q({ title })} on ${dayName(day)} ${dayNum(day)}`, () => addTidy(day, title, order));
  }
  function tickTidy(t: Tidy, done: boolean) {
    tidies = tidies.map((x) => (x.id === t.id ? { ...x, is_done: done } : x)); // at once; the reload confirms it
    return change(done ? `Ticked off ${q(t)}` : `Unticked ${q(t)}`, () => saveTidy(t.id, { is_done: done }));
  }
  function moveTidy(t: Tidy, to: string) {
    if (!to || to === t.day) return;
    // goes to the end of that day's list; its follow-ons (and what it follows) not ticked go along, as many days
    if (followsOf(t) || followOnsOf(t).length) {
      return change(`Moved ${q(t)} to ${fmtDay(to)}, with what goes with it`, () => moveWithFollowOns(t, to));
    }
    return change(`Moved small task ${q(t)} to ${fmtDay(to)}`, () => saveTidy(t.id, { day: to, sort_order: null }));
  }
  async function renameTidy() {
    const e = tidyEdit;
    tidyEdit = null;
    const t = e && tidies.find((x) => x.id === e.id);
    const title = e?.title.trim();
    if (!t || !title || title === t.title) return;
    await change(`Renamed small task ${q(t)}`, () => saveTidy(t.id, { title }));
  }
  function removeTidy(t: Tidy) {
    // what follows it on follows the one before it instead (or nothing)
    const relink = followOnsOf(t).length ? () => unlinkFollowOns(t) : async () => {};
    // one of a series: hidden, so it is not made again; the series goes on
    if (t.repeat_id) {
      return change(`Deleted ${q(t)} on ${fmtDay(t.day)} (the series goes on)`,
        async () => { await relink(); await saveTidy(t.id, t.follows ? { skipped: true, follows: null } : { skipped: true }); });
    }
    return change(`Deleted small task ${q(t)}`, async () => { await relink(); await deleteTidy(t.id); }); // Undo brings it back
  }

  // ---- follow-ons (0072_tidy_follow.sql): another small task that goes with this one ----------
  const allTidies = $derived([...tidies, ...tidyLinked]);
  const followsOf = (t: Tidy) => (t.follows ? allTidies.find((x) => x.id === t.follows) : undefined);
  const followOnsOf = (t: Tidy) => allTidies.filter((x) => x.follows === t.id)
    .sort((a, b) => a.day.localeCompare(b.day) || tidyOrder(a, b));
  let followTitle = $state("");
  let followDate = $state("");
  async function makeFollowOn(t: Tidy, title: string, day: string) {
    title = title.trim();
    if (!title || !day) return;
    const order = Math.max(0, ...tidiesOn(day).map((x) => x.sort_order ?? 0)) + 10;
    const ok = await change(`Added ${q({ title })}, a follow-on to ${q(t)}`, () => addFollowOn(t, day, title, order));
    if (!ok && noFollows(error)) error = "Follow-ons need web/db/0072_tidy_follow.sql run first, in the Supabase SQL editor.";
  }
  function unfollow(t: Tidy) {
    const p = followsOf(t);
    return change(`${q(t)} no longer follows on from ${p ? q(p) : "another"}`, () => saveTidy(t.id, { follows: null }));
  }
  // going to the other one: lit up, in its week (or month) if it is not on screen
  let showTidy: string | null = null;
  function goToTidy(x: Tidy) {
    tidyMenu = null;
    if (tidies.some((t) => t.id === x.id) && (monthView || days.includes(x.day))) {
      if (phone && !monthView) pickedDay = x.day;
      return lightTidy(x.id);
    }
    showTidy = x.id;
    pickedDay = x.day;
    if (monthView) monthAt = `${x.day.slice(0, 7)}-01`;
    else offset = Math.round((daysIn({ from: weekStart(today()), to: weekStart(x.day) }) - 1) / 7);
  }
  function lightTidy(id: string) {
    showTidy = null;
    lit = id;
    tick().then(() => document.querySelector(`.tidy-row[data-id="${id}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" }));
    setTimeout(() => { if (lit === id) lit = null; }, 2500);
  }
  const shortDay = (d: string) =>
    `${dayName(d)} ${dayNum(d)}${d.slice(0, 7) === today().slice(0, 7) ? "" : ` ${parse(d).toLocaleDateString("en-GB", { month: "short" })}`}`;

  // ---- repeating small tasks (lib/repeat.ts) ----------------------------------------
  let repeatWay = $state<Every>("year");
  async function makeRepeat(t: Tidy, way: { every: Every; month: number | null; day: number }) {
    const ok = await change(`${q(t)} repeats ${describeRepeat(way)}`, () => startRepeat(t, way));
    if (!ok && /repeat/i.test(error)) error = "Repeating small tasks need web/db/0071_tidy_repeat.sql run first, in the Supabase SQL editor.";
  }
  /** Stop a series after a day: its tasks up to then stay; later ones not ticked go. */
  function endRepeat(r: Repeat, after: string) {
    return change(`Stopped repeating ${q(r)} after ${fmtDay(after)}`, () => stopRepeat(r.id, after));
  }
  // a link on a small task: any web address (an email in Outlook on the web, a document, a form…)
  let linkDraft = $state("");
  async function setTidyLink(t: Tidy, link: string | null) {
    const ok = await change(link ? `Linked ${q(t)}` : `Took the link off ${q(t)}`, () => saveTidy(t.id, { link }));
    if (!ok && /link/i.test(error)) error = "Links on small tasks need web/db/0063_tidy_link.sql run first, in the Supabase SQL editor.";
  }

  function openTidyMenu(ev: MouseEvent, t: Tidy) {
    ev.preventDefault();
    ev.stopPropagation();
    menu = null;
    tidyMenu = { t, ...menuAt(ev) };
  }
  function tidyItems(t: Tidy): Item[] {
    const r = repeatOf(t);
    const repeating: Item[] = r
      ? [
          { label: `↻ Repeats ${describeRepeat(r)}`, run: () => (panel = { kind: "repeats" }) },
          ...(!r.until || r.until > (t.repeat_on ?? t.day)
            ? [{ label: "Stop repeating after this one", run: () => endRepeat(r, t.repeat_on ?? t.day) }]
            : []),
        ]
      : repeats
        ? [{ label: "↻ Repeat…", run: () => { repeatWay = "year"; panel = { kind: "repeat", tidy: t }; } }]
        : [];
    return [
      { label: "‹ Move to the day before", run: () => moveTidy(t, addDays(t.day, -1)) },
      { label: "Move to the day after ›", run: () => moveTidy(t, addDays(t.day, 1)) },
      { label: "Move to a date…", run: () => { moveDate = t.day; panel = { kind: "tidyMove", tidy: t }; } },
      { label: "+ Follow-on…", run: () => { followTitle = ""; followDate = t.day; panel = { kind: "followOn", tidy: t }; } },
      ...(followsOf(t) ? [{ label: `← Go to “${followsOf(t)!.title}”`, run: () => goToTidy(followsOf(t)!) }] : []),
      ...followOnsOf(t).map((x) => ({ label: `→ Go to “${x.title}”`, run: () => goToTidy(x) })),
      ...(t.follows ? [{ label: "Unlink from the one before", run: () => unfollow(t) }] : []),
      { label: t.is_tidy ? "☑ Tidy-up" : "☐ Tidy-up", run: () => setTidyUp(t, !t.is_tidy) },
      { label: "Rename", run: () => (tidyEdit = { id: t.id, title: t.title }) },
      { label: t.link ? "Change link…" : "Add link…", run: () => { linkDraft = t.link ?? ""; panel = { kind: "tidyLink", tidy: t }; } },
      ...(t.link ? [{ label: "Remove link", run: () => setTidyLink(t, null) }] : []),
      ...repeating,
      { label: r ? "Delete this one" : "Delete", run: () => removeTidy(t), danger: true },
    ];
  }
  function focusSelect(node: HTMLInputElement) {
    node.focus();
    node.select();
  }

  // ---- card menu: click or right-click a card ------------------------------------------
  // The cards stay quiet (title, tick, status); their actions live in one menu.
  // `sub`: one of its groups (Move…, Cancel / change status…) shown in its place
  type Sub = "move" | "status";
  type Menu = { slot: Slot; day: string; x: number; y: number; sub?: Sub };
  // `go`: opens a group (or, "main", goes back to the whole menu) instead of running
  type Item = { label: string; run?: () => unknown; danger?: boolean; go?: Sub | "main" };
  let menu = $state<Menu | null>(null);
  const MENU_W = 220;
  const MENU_H = 420; // a small task's menu, with its repeat items, is the tallest

  /** Where a menu opens: at the pointer for a right-click, under the thing clicked otherwise. */
  function menuAt(ev: MouseEvent): { x: number; y: number } {
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
    return {
      x: Math.max(8, Math.min(x, window.innerWidth - MENU_W - 8)),
      y: Math.max(8, Math.min(y, window.innerHeight - MENU_H - 8)),
    };
  }
  function openMenu(ev: MouseEvent, slot: Slot, day: string) {
    ev.preventDefault();
    ev.stopPropagation();
    tidyMenu = null;
    menu = { slot, day, ...menuAt(ev) };
  }
  const closeMenu = () => { menu = null; tidyMenu = null; };

  // a card's project (its logged entry's, once logged) in the Logbook, at its milestone;
  // the browser's Back, or the Logbook's link, comes back to this week
  function logbookItem(s: Slot, t: Todo): Item[] {
    const e = s.entry_id ? entryById.get(s.entry_id) : undefined;
    const p = e?.project_id ?? t.project_id;
    if (!p) return [];
    const m = (e?.project_id ? e.milestone_id : t.milestone_id) ?? "";
    return [{ label: "Open in Logbook ›", run: () => toLogbook(p, m) }];
  }
  function toLogbook(project: string, milestone: string | null) {
    history.replaceState(null, "", `#/week?w=${start}`);
    location.hash = `#/logbook?p=${project}${milestone ? `&m=${milestone}` : ""}&w=${start}`;
  }

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
      return [...(meeting ? agendaItem(t, m.day) : []), ...done, ...another, ...restItems, ...(e ? [{ label: "Open logged entry", run: () => openEntry(e, m.day) }] : []),
              ...logbookItem(s, t), edit, remove];
    }
    const back: Item = { label: "‹ Back", go: "main" };
    if (m.sub === "move") {
      return [
        back,
        { label: "‹ Move to the day before", run: () => move(s, -1) },
        { label: "Move to the day after ›", run: () => move(s, 1) },
        { label: "Move to a date…", run: () => openMoveTo(t, s) },
      ];
    }
    if (m.sub === "status") {
      return [
        back,
        { label: meeting ? "Cancel meeting (keep, struck through)" : "Cancel this day (keep, struck through)", run: () => setCancelled(s, true) },
        ...(meeting ? [] : [{ label: "Cancel the whole to-do (keep, struck through)", run: () => cancelTodo(t) }]),
        remove,
        ...(meeting ? [] : [{ label: "Delete the to-do", run: () => deleteWhole(t), danger: true }]),
        ...(t.is_tentative ? [] : [tentativeItem]),
      ];
    }
    return [
      ...(t.is_tentative ? [tentativeItem] : []),
      { label: "✓ Log time", run: () => openLog(t, s, m.day) },
      ...(meeting ? agendaItem(t, m.day) : []),
      ...logbookItem(s, t),
      edit,
      ...done,
      ...(meeting ? [] : [{ label: "+ Another session on this day", run: () => addSession(t, m.day) }]),
      ...(meeting ? [] : [{ label: "Move… ›", go: "move" as const }]),
      { label: "Cancel / change status… ›", go: "status" },
      ...(meeting ? [] : [{ label: "Plan across days…", run: () => openSpread(t) }]),
      ...fromOutlook,
    ];
  }

  // (Ctrl/Cmd+Z is the app's, for every tab.)
  function keys(ev: KeyboardEvent) {
    if (menu || tidyMenu) return menuKeys(ev);
  }

  function focusFirst(node: HTMLElement) {
    (node.querySelector("button") as HTMLButtonElement | null)?.focus();
  }
  function menuKeys(ev: KeyboardEvent) {
    if (!menu && !tidyMenu) return;
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
    | { kind: "tidyMove"; tidy: Tidy }
    | { kind: "followOn"; tidy: Tidy }
    | { kind: "tidyLink"; tidy: Tidy }
    | { kind: "repeat"; tidy: Tidy }
    | { kind: "repeats" }
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

  function arriveFromDay(f: NonNullable<typeof fromDay>) {
    fromDay = null;
    const t = todos.find((x) => x.id === f.todo);
    const idea = ideas.find((x) => x.id === f.idea);
    const e = entries.find((x) => x.id === f.entry);
    let at: string | null = null; // what to bring into view
    if (e) openEntry(e, f.day);
    else if (t) panel = { kind: "todo", todo: t };
    else if (idea) {
      if (phone) showView("todos");
      const n = ideaNotes.find((x) => x.id === f.note);
      if (n) startNote(idea, n);
      else editIdea(idea);
      at = `li.idea[data-id="${idea.id}"]`;
    } else if (f.tidy && tidies.some((x) => x.id === f.tidy)) {
      if (phone) showView("calendar");
      lit = f.tidy;
      at = `.tidy-row[data-id="${f.tidy}"]`;
      setTimeout(() => (lit = null), 2500);
    }
    if (at) tick().then(() => document.querySelector(at!)?.scrollIntoView({ block: "center", behavior: "smooth" }));
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
      if (markedDone) {
        await saveTodo(p.todo.id, { is_done: true, done_at: new Date().toISOString() });
        const ms = milestoneFollows(p.todo, true);
        if (ms) await setMilestoneStatus(ms, "done");
      }
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
  // or turned into a to-do for the week. A cancelled one stays, struck through.
  let ideas = $state<Todo[]>([]);
  const openIdeas = $derived(ideas.filter((t) => !t.is_cancelled).length);
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

  // clicking an idea's text, or a note's, edits it; a link in it still opens, and
  // text being selected to copy stays selected
  function clickEdit(ev: MouseEvent, edit: () => void) {
    if ((ev.target as HTMLElement).closest("a") || getSelection()?.toString()) return;
    edit();
  }
  /** An editor opens ready to type, the cursor after what is there. */
  function ready(el: HTMLInputElement | HTMLTextAreaElement) {
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
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
  // the row starts unticked, but it can still be added (e.g. a different task on it).
  // `done`: marked done here (saved at once, as in Planning) — it stays listed, struck through
  type MsRow = { p: Project; m: Milestone; info: MilestoneWeek; existing: Todo | null; pick: boolean; hours: number | null; must: boolean; done: boolean };
  let msRows = $state<MsRow[]>([]);
  let msLoading = $state(false);
  // which sections are open: set once when the window opens (urgent ones),
  // then only by you — ticking a box must not fold its section
  let msOpen = $state<Record<string, boolean>>({});

  // What you tick, type and choose is kept (in this browser) until you add them, so the
  // window opens again as you left it for the same week — after closing it, a reload, or a
  // trip to Planning. Hours you hadn't changed are worked out again.
  type MsKept = { week: string; rows: { id: string; pick: boolean; must: boolean; hours?: number | null }[] };
  let msWeek = "";
  $effect(() => {
    if (msLoading || !msRows.length) return;
    const kept: MsKept = { week: msWeek, rows: msRows.map((r) => ({
      id: r.m.id, pick: r.pick, must: r.must, hours: r.hours === r.info.suggested ? undefined : r.hours,
    })) };
    try { localStorage.setItem(MS_PICKS, JSON.stringify(kept)); } catch {}
  });
  async function openMilestones() {
    panel = { kind: "milestones" };
    msLoading = true;
    msRows = [];
    msWeek = start;
    let left: MsKept["rows"] = [];
    try {
      const kept = JSON.parse(localStorage.getItem(MS_PICKS) ?? "null") as MsKept | null;
      if (kept?.week === start) left = kept.rows;
    } catch {}
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
          rows.push({ p, m, info, existing, pick: !existing && urgent, hours: info.suggested, must: m.hard_deadline || urgent, done: false });
        }
      }
      for (const k of left) {
        const r = rows.find((x) => x.m.id === k.id);
        if (!r) continue;
        r.pick = k.pick;
        r.must = k.must;
        if (k.hours !== undefined) r.hours = k.hours;
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
          projects: [...byProject.values()].sort((x, y) => byPlanningOrder(x.p, y.p)),
        });
      }
    }
    return out;
  });
  const pickedIn = (rows: MsRow[]) => rows.filter((r) => r.pick).length;
  function pickAll(rows: MsRow[], on: boolean) {
    for (const r of rows) r.pick = on && !r.done;
  }
  // going to a milestone in Planning: its link there, or the browser's Back, comes back
  // to this week with the window open again (a Ctrl+click opens a new tab and leaves this one be)
  function leaveForPlanning(ev: MouseEvent) {
    if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) return;
    history.replaceState(null, "", `#/week?w=${start}&ms=1`);
  }
  async function msDone(r: MsRow, done: boolean) {
    if (await change(done ? `Marked ${q(r.m)} done` : `Reopened ${q(r.m)}`, () => setMilestoneStatus(r.m.id, done ? "done" : "active"))) {
      r.done = done;
      if (done) r.pick = false;
    }
  }

  async function addFromMilestones() {
    const picked = msRows.filter((r) => r.pick);
    if (!picked.length) return;
    if (await change(`Added ${picked.length} to-${picked.length === 1 ? "do" : "dos"} from milestones`, async () => {
      for (const r of picked) {
        await saveTodo(null, {
          kind: "task", title: r.m.title, due_on: isCurrent ? today() : start,
          category_id: r.p.category_id, project_id: r.p.id, milestone_id: r.m.id,
          est_hours: r.hours, must_this_week: r.must,
        });
      }
    })) {
      // added: the next time starts afresh
      msRows = [];
      try { localStorage.removeItem(MS_PICKS); } catch {}
    }
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
  let fwdSaving = $state<string | null>(null);
  let fwdError = $state("");
  let fwdTo = $state(""); // the week they go into: the one on screen, or the next
  let fwdCanDrop = $state(true); // false until 0056 is run
  let fwdShowDropped = $state(false);
  // dropped ones are listed apart: not offered, but still there to bring forward or put back
  const fwdMain = $derived(fwdRows.filter((r) => !r.t.carry_skip));
  const fwdDropped = $derived(fwdRows.filter((r) => r.t.carry_skip));
  const fwdWeeks = $derived([...new Set(fwdMain.map((r) => r.week))]);

  async function openForward(to: string = start) {
    panel = { kind: "forward" };
    fwdTo = to;
    fwdLoading = true;
    fwdError = "";
    fwdRows = [];
    try {
      const plan = await loadUnfinishedBefore(to);
      if (fwdTo !== to) return; // the choice changed while this was loading
      fwdSlots = plan.slots;
      fwdCanDrop = plan.canDrop;
      fwdRows = [...plan.todos, ...plan.dropped].map((t) => ({
        t, pick: false, week: weekStart(t.due_on),
        loggedDays: plan.slots.filter((s) => s.todo_id === t.id && s.entry_id).length,
      }));
    } catch (e) {
      error = (e as Error).message;
    } finally {
      fwdLoading = false;
    }
  }
  async function finishForward(t: Todo) {
    if (fwdSaving) return;
    fwdSaving = t.id;
    fwdError = "";
    try {
      if (await setDone(t, true)) {
        fwdRows = fwdRows.filter((r) => r.t.id !== t.id);
      } else {
        fwdError = error;
      }
    } finally {
      fwdSaving = null;
    }
  }
  /** Drop: no longer offered here, but left as it is — open, on its own week. Put back offers it again. */
  async function dropForward(r: FwdRow, drop: boolean) {
    if (fwdSaving) return;
    fwdSaving = r.t.id;
    fwdError = "";
    try {
      if (await change(drop ? `Dropped ${q(r.t)} from carrying forward` : `Put ${q(r.t)} back to carry forward`,
                       () => saveTodo(r.t.id, { carry_skip: drop }))) {
        r.t = { ...r.t, carry_skip: drop };
        r.pick = false;
      } else {
        fwdError = error;
      }
    } finally {
      fwdSaving = null;
    }
  }
  async function forwardPicked() {
    if (fwdSaving) return;
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
          await saveTodo(t.id, { due_on: to, ...(t.carry_skip ? { carry_skip: false } : {}) });
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

  {#if phone}
    <div class="m-switch" role="tablist" aria-label="Show">
      <button role="tab" aria-selected={mobileView === "calendar"} class:on={mobileView === "calendar"}
              onclick={() => showView("calendar")}>Calendar</button>
      <button role="tab" aria-selected={mobileView === "todos"} class:on={mobileView === "todos"}
              onclick={() => showView("todos")}>To-dos{#if groups[0].rows.length + groups[1].rows.length}<span class="m-count">{groups[0].rows.length + groups[1].rows.length}</span>{/if}</button>
    </div>
  {/if}

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
      {#if weekTotals.unplanned >= 0.01}
        <span class="wt-sub" title="Logged on nothing planned this week (no card): counted in Logged and in % of target, not in % of planned">incl. {fmtHours(weekTotals.unplanned)} unplanned</span>
      {/if}
      {#if weekTotals.plan || weekTotals.target}
        <span class="wt-sub">
          {#if weekTotals.plan}<span title="Logged on the plan (cards logged), against that plus what is still to do (cards not yet logged, and must-dos' hours left). Unplanned time is left out.">{Math.round((100 * weekTotals.loggedPlanned) / weekTotals.plan)}% of planned</span>{/if}{weekTotals.plan && weekTotals.target ? " · " : ""}{#if weekTotals.target}{Math.round((100 * weekTotals.logged) / weekTotals.target)}% of target{/if}
        </span>
      {/if}
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
    <button onclick={() => openMilestones()} title="To-dos from milestones that fall in this week">+ From milestones</button>
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
  {#if !phone || mobileView === "calendar"}
  {#if !tidyMissing}
    <div class="cal-switch" role="group" aria-label="Calendar">
      <button class:on={!monthView} aria-pressed={!monthView} onclick={() => setMonthView(false)}>Week</button>
      <button class:on={monthView} aria-pressed={monthView} onclick={() => setMonthView(true)}>Month · small tasks</button>
    </div>
    {#if repeats}
      <button class="repeat-open" title="Small tasks that repeat: every month, every year, or by the lunar calendar"
              onclick={() => (panel = { kind: "repeats" })}>↻ Repeating{repeats.length ? ` (${repeats.filter((r) => !r.until || r.until >= today()).length})` : ""}</button>
    {/if}
  {/if}
  {#if monthView && !tidyMissing}
    {@render monthGrid()}
  {:else}
  {#if phone}
    <div class="m-days" role="tablist" aria-label="Day">
      {#each days as d (d)}
        {@const plan = plannedOn(d)}
        <button role="tab" aria-selected={d === phoneDay} class:on={d === phoneDay} class:today={d === today()}
                onclick={() => (pickedDay = d)}>
          <span class="m-dname">{dayName(d)}</span>
          <strong>{dayNum(d)}</strong>
          <span class="m-dh">{plan.hours ? fmtHours(plan.hours) : "·"}</span>
        </button>
      {/each}
    </div>
  {/if}
  <div class="days">
    {#each shownDays as d (d)}
      {@const meetings = slotsOn(d, "meeting")}
      {@const duties = dutiesOn(d)}
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
               class:tentative={tentative(t)} class:lit={lit === t.id} data-todo={t.id}
               role="group" oncontextmenu={(ev) => openMenu(ev, s, d)}>
            <button class="card-body" aria-haspopup="menu" title="Actions (click or right-click)"
                    onclick={(ev) => openMenu(ev, s, d)}>
              <span class="time">{hhmm(s.start_time)}–{hhmm(s.end_time)}</span>
              <span class="title">{t.is_core ? "🎯 " : ""}{t.title}{#if agendaOf.has(t.id)}<span class="has-agenda" title="Has an agenda in Meetings"> 📋</span>{/if}</span>
              {#if label(t)}<span class="sub">{label(t)}</span>{/if}
              {#if s.is_cancelled}<span class="off">cancelled</span>{:else if s.entry_id}<span class="ok">✓ logged</span>{:else if pending(t)}<span class="off">from Outlook — to review{t.source_tentative ? " · tentative" : ""}</span>{:else if tentative(t)}<span class="off">tentative</span>{/if}
            </button>
          </div>
        {/each}

        {#each duties as s (s.id)}
          {@const t = todoById.get(s.todo_id)!}
          {@const e = s.entry_id ? entryById.get(s.entry_id) : null}
          {@const h = cardHours(s, t)}
          {@const left = t.is_done || s.is_cancelled || pending(t) ? null : leftFor(t)}
          {@const leftShown = left !== null && fmtHours(left) !== fmtHours(h ?? 0) ? leftText(left) : ""}
          <div class="card duty" class:logged={!!s.entry_id} class:done={t.is_done}
               class:cancelled={s.is_cancelled} class:review={pending(t)} class:tentative={tentative(t)}
               class:stale={!s.entry_id && !s.is_cancelled && !t.is_done && d < today()}
               class:sortable={duties.length > 1} class:dragging={dayDrag?.id === s.id}
               data-id={s.id} data-day={d}
               role="group" oncontextmenu={(ev) => openMenu(ev, s, d)}>
            {#if duties.length > 1}
              <button class="grip" title="Drag to reorder (or use ↑ ↓)" aria-label={`Move “${t.title}”: drag, or press up or down`}
                      onpointerdown={(ev) => startCardDrag(ev, s)}
                      onkeydown={(ev) => cardKeyMove(ev, s)}>⠿</button>
            {/if}
            <button class="card-body" aria-haspopup="menu" title="Actions (click or right-click)"
                    onclick={(ev) => openMenu(ev, s, d)}>
              <span class="title">{t.must_this_week ? "● " : ""}{t.is_core ? "🎯 " : ""}{t.title}</span>
              {#if label(t) || h || leftShown}<span class="sub">{[label(t), h ? fmtHours(h) : "", leftShown].filter(Boolean).join(" · ")}</span>{/if}
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

        {#if !tidyMissing}{@render tidyList(d)}{/if}
      </div>
    {/each}
  </div>
  {/if}
  <div class="below-days">
    <button onclick={openEmail}>✉ Create email checks (Mon–Fri)</button>
    <button onclick={() => openForward()}>↪ Carry forward unfinished to-dos…</button>
  </div>
  {/if}

  <!-- ================= to-do list ================= -->
  {#if !phone || mobileView === "todos"}
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
        <div class="todo-list">
          <Sortable items={g.rows} onreorder={(order) => saveTodoOrder(g.title, order)} disabled={todoOrderSaving}>
          {#snippet row(t)}
            {@const ts = slotsOf(t)}
            {@const lh = loggedFor(t)}
            <div class="todo" class:cancelled={t.is_cancelled}>
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
                  {#if lh}{fmtHours(lh)}{t.est_hours ? ` of ${fmtHours(t.est_hours)}` : ""} logged{#if !t.is_done && !t.is_cancelled && leftFor(t) !== null} · {leftText(leftFor(t)!)}{/if}{:else if t.est_hours}est. {fmtHours(t.est_hours)}{/if}{#if notesOf(t).length}<span title="Comments — open the to-do to read or add">{label(t) || lh || t.est_hours ? " · " : ""}💬 {notesOf(t).length}</span>{/if}
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
            </div>
          {/snippet}
          </Sortable>
        </div>
      </div>
    {/if}
  {/each}

  <!-- ================= to think about ================= -->
  {#snippet linked(text: string)}<Linked {text} />{/snippet}
  {#snippet editable(cls: string, text: string, edit: () => void)}
    <span class="editable {cls}" role="button" tabindex="0" title="Click to edit"
          onclick={(ev) => clickEdit(ev, edit)}
          onkeydown={(ev) => { if (ev.target === ev.currentTarget && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); edit(); } }}>{@render linked(text)}</span>
  {/snippet}
  {#snippet noteBox(t: Todo)}
    <div class="note-box">
      <textarea rows="3" bind:value={noteText} placeholder="Develop it — notes, options, who to ask…" aria-label="Note"
                use:ready onkeydown={(ev) => noteKeys(ev, t)}></textarea>
      {#if noteError}<p class="error">Not saved: {noteError}</p>{/if}
      <div class="t-acts">
        <button class="mini primary" onclick={() => saveNote(t)} disabled={!noteText.trim()}>Save</button>
        <button class="mini" onclick={stopNote}>Cancel</button>
        <span class="muted small">Ctrl+Enter saves</span>
      </div>
    </div>
  {/snippet}
  <div class="group ideas">
    <h3>To think about {#if openIdeas}<span class="muted small">{openIdeas}</span>{/if}</h3>
    <form class="idea-add" onsubmit={addIdea}>
      <input bind:value={ideaText} placeholder="Jot down a thought — paste a web address and it shows as a short “link”" aria-label="New idea" />
      <button type="submit" disabled={!ideaText.trim()}>Add</button>
    </form>
    <ul class="todos">
      {#each shownIdeas as t (t.id)}
        <li class="idea" class:dragging={dragId === t.id} class:cancelled={t.is_cancelled} data-id={t.id}>
          {#if ideaEditing === t.id}
            <div class="idea-edit">
              <input bind:value={ideaDraft.title} aria-label="Idea" use:ready
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
              {@render editable("idea-title", t.title, () => editIdea(t))}
              {#if t.note}{@render editable("idea-note", t.note, () => editIdea(t))}{/if}
              <span class="t-meta muted">jotted {fmtDay(t.due_on)}</span>
              {#if notesOf(t).length}
                <ul class="inotes">
                  {#each notesOf(t) as n (n.id)}
                    <li>
                      {#if noteEditing === n.id}
                        {@render noteBox(t)}
                      {:else}
                        {@render editable("idea-note", n.body, () => startNote(t, n))}
                        <span class="t-meta muted">{fmtDay(n.created_at.slice(0, 10))}</span>
                        <button class="link" aria-label="Delete note" title="Delete note" onclick={() => deleteNote(t, n)}>✕</button>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}
              {#if noteFor === t.id}{@render noteBox(t)}{/if}
            </div>
            <div class="t-acts">
              {#if t.is_cancelled}
                <span class="muted small">cancelled</span>
                <button class="mini" onclick={() => restore(t)}>Restore</button>
                <button class="mini danger" title="Delete for good" onclick={() => deleteIdea(t)}>Delete</button>
              {:else}
                <button class="mini" title="Add a note to develop it" onclick={() => startNote(t)}>+ Note</button>
                <button class="mini" title="Make it a to-do for this week" onclick={() => ideaToTodo(t)}>→ To-do</button>
                <button class="mini" title="Thought through — take it off the list" onclick={() => ideaDone(t)}>Done</button>
                <button class="mini" title="Cancel — stays here, struck through" onclick={() => cancelTodo(t)}>Cancel</button>
                <button class="mini danger" aria-label="Delete" title="Delete" onclick={() => deleteIdea(t)}>✕</button>
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  </div>

  {/if}

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

{#if agendaBack}<BackLink href={agendaBack} text="Back to the agenda" />{/if}

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
  {#key m.sub}
    <div class="menu" role="menu" style:left={`${m.x}px`} style:top={`${m.y}px`} use:focusFirst>
      {#each menuItems(m) as item (item.label)}
        <button role="menuitem" class:danger={item.danger} class:back={item.go === "main"}
                aria-haspopup={item.go && item.go !== "main" ? "menu" : undefined}
                onclick={() => {
                  if (item.go) menu = { ...m, sub: item.go === "main" ? undefined : item.go };
                  else { closeMenu(); item.run?.(); }
                }}>{item.label}</button>
      {/each}
    </div>
  {/key}
{/if}

{#snippet tidyList(d: string, short = false)}
  {@const list = tidiesOn(d)}
  <div class="tidy" role="group" aria-label={`Small tasks / deadlines on ${dayName(d)} ${dayNum(d)}`}>
    {#each list as t (t.id)}
      <div class="tidy-row" class:done={t.is_done} class:tidyup={t.is_tidy} class:dragging={tidyDrag?.id === t.id} class:lit={lit === t.id}
           data-id={t.id} data-day={d}>
        {#if list.length > 1}
          <button type="button" class="tgrip" title="Drag to reorder (or use ↑ ↓)" aria-label={`Move “${t.title}”: drag, or press up or down`}
                  onpointerdown={(ev) => startTidyDrag(ev, t)} onkeydown={(ev) => tidyKeyMove(ev, t)}>⠿</button>
        {/if}
        <input type="checkbox" checked={t.is_done} aria-label={`Done: ${t.title}`}
               onchange={(ev) => tickTidy(t, ev.currentTarget.checked)} />
        {#if tidyEdit?.id === t.id}
          <input class="tidy-input" bind:value={tidyEdit.title} aria-label="Rename small task" use:focusSelect
                 onkeydown={(ev) => {
                   if (ev.key === "Enter") { ev.preventDefault(); renameTidy(); }
                   if (ev.key === "Escape") { ev.preventDefault(); tidyEdit = null; }
                 }}
                 onblur={renameTidy} />
        {:else}
          <button class="tidy-title" aria-haspopup="menu" title={t.title}
                  onclick={(ev) => openTidyMenu(ev, t)} oncontextmenu={(ev) => openTidyMenu(ev, t)}>{t.title}</button>
          {@const before = followsOf(t)}
          {@const after = followOnsOf(t)}
          {#if before}
            <button type="button" class="tidy-follow" onclick={() => goToTidy(before)}
                    title={`Follows on from “${before.title}” (${shortDay(before.day)}) — go to it`}
                    aria-label={`Go to “${before.title}”, which this follows on from`}>←</button>
          {/if}
          {#each after as x (x.id)}
            <button type="button" class="tidy-follow" onclick={() => goToTidy(x)}
                    title={`Followed by “${x.title}” (${shortDay(x.day)}) — go to it`}
                    aria-label={`Go to its follow-on “${x.title}”`}>→</button>
          {/each}
          {#if t.repeat_id}
            {@const r = repeatOf(t)}
            <span class="tidy-repeat" title={r ? `Repeats ${describeRepeat(r)}` : "Repeats"} aria-label="Repeats">↻</span>
          {/if}
          {#if t.link}
            <a class="tidy-link" href={t.link} target="_blank" rel="noopener noreferrer" title={`Open ${t.link}`}
               aria-label={`Open the link for “${t.title}”`}>🔗</a>
          {/if}
        {/if}
      </div>
    {/each}
    <input class="tidy-input tidy-add" placeholder={short ? "+ add" : "+ task / deadline"} bind:value={tidyDraft[d]}
           aria-label={`Add a small task or deadline on ${dayName(d)} ${dayNum(d)}`}
           onkeydown={(ev) => { if (ev.key === "Enter") { ev.preventDefault(); addTidyOn(d); } }} />
  </div>
{/snippet}

{#snippet monthGrid()}
  <section class="month" aria-label={`Small tasks / deadlines, ${monthLabel}`}>
    <div class="month-nav">
      <button aria-label="The month before" onclick={() => (monthAt = shiftMonth(monthFirst, -1))}>‹</button>
      <h2>{monthLabel}</h2>
      <button aria-label="The month after" onclick={() => (monthAt = shiftMonth(monthFirst, 1))}>›</button>
      {#if monthFirst !== thisMonth}<button class="link" onclick={() => (monthAt = thisMonth)}>This month</button>{/if}
      <span class="muted small">{tidies.filter((t) => t.day >= monthFirst && t.day <= monthLast && !t.is_done).length} open</span>
    </div>
    {#if phone}
      {#key monthFirst}
        <div class="month-list" use:toToday>
          {#each monthDays as d (d)}
            <div class="m-cell" class:today={d === today()} class:past={d < today()} class:empty={!tidiesOn(d).length}>
              <div class="m-date">{dayName(d)} <strong>{dayNum(d)}</strong></div>
              {@render tidyList(d)}
            </div>
          {/each}
        </div>
      {/key}
    {:else}
      <div class="month-scroll">
        <div class="month-grid">
          {#each gridDays.slice(0, 7) as d (d)}<div class="m-dow">{dayName(d)}</div>{/each}
          {#each gridDays as d (d)}
            <div class="m-cell" class:out={d < monthFirst || d > monthLast} class:today={d === today()} class:past={d < today()}>
              <div class="m-date">{dayNum(d) === 1 ? parse(d).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : dayNum(d)}</div>
              {@render tidyList(d, true)}
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </section>
{/snippet}

{#if tidyMenu}
  {@const tm = tidyMenu}
  <div class="menu-backdrop" role="presentation" onclick={closeMenu}
       oncontextmenu={(ev) => { ev.preventDefault(); closeMenu(); }}></div>
  <div class="menu" role="menu" style:left={`${tm.x}px`} style:top={`${tm.y}px`} use:focusFirst>
    {#each tidyItems(tm.t) as item (item.label)}
      <button role="menuitem" class:danger={item.danger} onclick={() => { closeMenu(); item.run?.(); }}>{item.label}</button>
    {/each}
  </div>
{/if}

<dialog bind:this={dialog} onclose={() => (panel = null)}>
  {#if panel && tax}
    {#if panel.kind === "todo"}
      <h2>{panel.todo ? `Edit ${panel.todo.kind === "meeting" ? "meeting" : "to-do"}` : panel.as === "meeting" ? "New meeting" : "New to-do"}</h2>
      <TodoForm todo={panel.todo} slots={panel.todo ? slotsOf(panel.todo) : []} {tax} {projects}
                weekStart={start} day={panel.day} placeOnDay={panel.place} kind={panel.as}
                onsaved={closed} oncancel={() => (panel = null)}
                oncomments={() => loadIdeaNotes().then((n) => (ideaNotes = n)).catch(() => {})} />
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
                        <li class:off={!!r.existing && !r.pick} class:done={r.done}>
                          <input type="checkbox" bind:checked={r.pick} disabled={r.done} aria-label={`Add ${r.m.title}`} />
                          <div class="ms-what">
                            <a class="ms-goto" href={`#/planning?m=${r.m.id}&w=${start}`} title="Show it in Planning" onclick={leaveForPlanning}><strong>{r.m.title}</strong></a>
                            {#if r.done}<span class="ms-done">✓ done</span>{/if}
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
                          {#if r.done}
                            <button class="mini" title="Not done after all" onclick={() => msDone(r, false)}>Reopen</button>
                          {:else}
                            <button class="mini" title="Mark the milestone done — saved at once" onclick={() => msDone(r, true)}>Done</button>
                          {/if}
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
    {:else if panel.kind === "tidyLink"}
      {@const lt = panel.tidy}
      {@const clean = cleanLink(linkDraft)}
      <h2>Link for “{lt.title}”</h2>
      <form class="move-to" onsubmit={(ev) => { ev.preventDefault(); const t = lt, to = clean; if (!to) return; panel = null; setTidyLink(t, to); }}>
        <label>Web address <input bind:value={linkDraft} placeholder="https://…" autocomplete="off" spellcheck="false" use:focusSelect /></label>
        <p class="muted small">
          {#if linkDraft.trim() && !clean}That isn't a web address: it should start with https://, http:// or mailto:.
          {:else}Paste any link — an email from Outlook on the web (… › Share › Copy link), a document, a form. 🔗 beside the
            task opens it in a new tab.{/if}
        </p>
        <div class="pick-actions">
          <button class="primary" type="submit" disabled={!clean || clean === lt.link}>Save link</button>
          <button type="button" onclick={() => (panel = null)}>Cancel</button>
        </div>
      </form>
    {:else if panel.kind === "tidyMove"}
      {@const mt = panel.tidy}
      <h2>Move “{mt.title}”</h2>
      <form class="move-to" onsubmit={(ev) => { ev.preventDefault(); const t = mt, to = moveDate; panel = null; moveTidy(t, to); }}>
        <label>To <input type="date" bind:value={moveDate} required /></label>
        <p class="muted small">Now on {fmtDay(mt.day)}. Any day will do, in this week or another.</p>
        <div class="pick-actions">
          <button class="primary" type="submit" disabled={!moveDate || moveDate === mt.day}>Move</button>
          <button type="button" onclick={() => (panel = null)}>Cancel</button>
        </div>
      </form>
    {:else if panel.kind === "followOn"}
      {@const ft = panel.tidy}
      <h2>Follow-on to “{ft.title}”</h2>
      <form class="move-to" onsubmit={(ev) => { ev.preventDefault(); const t = ft, title = followTitle, d = followDate; panel = null; makeFollowOn(t, title, d); }}>
        <label>What <input bind:value={followTitle} required placeholder="e.g. Chase a reply" use:focusSelect /></label>
        <label>On <input type="date" bind:value={followDate} required /></label>
        <p class="muted small">
          A small task of its own, linked to this one (on {fmtDay(ft.day)}). Move either, and the other moves by as many
          days, unless it is ticked. ← and → beside them go from one to the other.
        </p>
        <div class="pick-actions">
          <button class="primary" type="submit" disabled={!followTitle.trim() || !followDate}>Add</button>
          <button type="button" onclick={() => (panel = null)}>Cancel</button>
        </div>
      </form>
    {:else if panel.kind === "repeat"}
      {@const rt = panel.tidy}
      {@const ways = waysFrom(rt.day)}
      {@const way = ways.find((w) => w.every === repeatWay) ?? ways[0]}
      <h2>Repeat “{rt.title}”</h2>
      <form class="move-to" onsubmit={(ev) => { ev.preventDefault(); const t = rt, w = way; panel = null; makeRepeat(t, w); }}>
        <fieldset class="repeat-ways">
          <legend class="muted small">From {fmtDay(rt.day)}, a small task like this one</legend>
          {#each ways as w (w.every)}
            <label><input type="radio" name="repeat-way" value={w.every} bind:group={repeatWay} /> {describeRepeat(w)}</label>
          {/each}
        </fieldset>
        <p class="muted small">
          {#if way.note}{way.note} {/if}Next: {nextDates(way, rt.day, 3).map(fmtShort).join(" · ")}.
          Each is made as an ordinary small task — tick, move, rename or delete it on its own; deleting one leaves the series
          going. To stop the series, use the task's menu or <em>↻ Repeating</em>; what has come before stays.
        </p>
        <div class="pick-actions">
          <button class="primary" type="submit">Repeat</button>
          <button type="button" onclick={() => (panel = null)}>Cancel</button>
        </div>
      </form>
    {:else if panel.kind === "repeats"}
      {@const all = repeats ?? []}
      {@const going = all.filter((r) => !r.until || r.until >= today())}
      {@const stopped = all.filter((r) => r.until && r.until < today())}
      <h2>Repeating small tasks</h2>
      {#if !all.length}
        <p class="muted small">None yet. To make one, click a small task and choose <em>↻ Repeat…</em>.</p>
      {/if}
      {#if going.length}
        <ul class="repeat-list">
          {#each going as r (r.id)}
            {@const next = nextDates(r, addDays(today(), -1), 1)[0]}
            <li>
              <span class="r-main"><strong>{r.title}</strong>
                <span class="muted small">{describeRepeat(r)} · {next ? `next ${fmtShort(next)}` : "no more to come"}{r.until ? ` · stops after ${fmtShort(r.until)}` : ""}</span></span>
              {#if !r.until}
                <button type="button" class="danger" title="Its small tasks up to today stay; later ones not ticked go"
                        onclick={() => endRepeat(r, today())}>Stop</button>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
      {#if stopped.length}
        <h3 class="muted small">Stopped</h3>
        <ul class="repeat-list stopped">
          {#each stopped as r (r.id)}
            <li><span class="r-main">{r.title} <span class="muted small">{describeRepeat(r)} · last {fmtShort(r.until!)}</span></span></li>
          {/each}
        </ul>
      {/if}
      <p class="muted small">Stopping keeps the small tasks up to today; later ones not yet ticked are taken off.</p>
      <div class="pick-actions"><button type="button" onclick={() => (panel = null)}>Close</button></div>
    {:else if panel.kind === "outlook"}
      <h2>Outlook calendar</h2>
      <OutlookSettings oncancel={() => (panel = null)}
                       onsaved={async (changed) => { panel = null; feed = await loadFeed(); if (changed && feed?.ics_url) runSync(); }} />
    {:else if panel.kind === "forward"}
      <h2>Carry forward unfinished to-dos</h2>
      <div class="pick">
        <label class="pick-hours">Into the week of
          <select value={fwdTo} disabled={!!fwdSaving} onchange={(ev) => openForward((ev.target as HTMLSelectElement).value)}>
            <option value={start}>{fmtDay(start)} (on screen)</option>
            <option value={addDays(start, 7)}>{fmtDay(addDays(start, 7))} (the week after)</option>
          </select>
        </label>
        <p class="muted small">
          To-dos filed under any week before that one, neither done nor cancelled — choose the week after to send on
          the week on screen's leftovers. Tick the ones to bring; the rest stay where they are. A day planned for one
          before that week and never logged is cancelled (it stays on its day, struck through), so its hours move with
          the to-do. To take one off this list without bringing it: <em>Mark done</em>, or <em>Drop</em> — it stays
          where it is, open, and is listed under <em>Dropped</em> below, to bring forward or put back whenever you like.
        </p>
        {#if fwdError}<p class="error">Not saved: {fwdError}</p>{/if}
        {#if fwdLoading}
          <p class="muted">Loading…</p>
        {:else if !fwdRows.length}
          <p class="muted">Nothing unfinished before the week of {fmtDay(fwdTo)}.</p>
        {:else}
          {#if !fwdMain.length}
            <p class="muted">Nothing to carry forward into the week of {fmtDay(fwdTo)} but what you dropped.</p>
          {:else}
            <div class="small">
              <button class="link" onclick={() => fwdMain.forEach((r) => (r.pick = true))}>Tick all</button> ·
              <button class="link" onclick={() => fwdMain.forEach((r) => (r.pick = false))}>none</button>
            </div>
          {/if}
          {#each fwdWeeks as w (w)}
            <div class="fwd-week">
              <h3>Week of {fmtDay(w)}</h3>
              <ul class="fwd">
                {#each fwdMain.filter((r) => r.week === w) as r (r.t.id)}
                  <li>
                    <label>
                      <input type="checkbox" bind:checked={r.pick} />
                      <span>{r.t.must_this_week ? "● " : ""}{r.t.is_core ? "🎯 " : ""}{r.t.title}</span>
                      <span class="muted small">{fwdInfo(r)}</span>
                    </label>
                    {#if fwdSaving === r.t.id}
                      <span class="muted small">Saving…</span>
                    {:else}
                      <span class="fwd-acts">
                        <button class="mini" disabled={!!fwdSaving} aria-label={`Mark “${r.t.title}” done`}
                                onclick={() => finishForward(r.t)}>Mark done</button>
                        {#if fwdCanDrop}
                          <button class="mini" disabled={!!fwdSaving} aria-label={`Drop “${r.t.title}” from this list`}
                                  title="Not offered here again: it stays where it is, open (not done, not cancelled), under Dropped below."
                                  onclick={() => dropForward(r, true)}>Drop</button>
                        {/if}
                      </span>
                    {/if}
                  </li>
                {/each}
              </ul>
            </div>
          {/each}
          {#if fwdDropped.length}
            <div class="fwd-week">
              <button class="link" aria-expanded={fwdShowDropped} onclick={() => (fwdShowDropped = !fwdShowDropped)}>
                {fwdShowDropped ? "▾" : "▸"} Dropped ({fwdDropped.length})
              </button>
              {#if fwdShowDropped}
                <ul class="fwd">
                  {#each fwdDropped as r (r.t.id)}
                    <li>
                      <label>
                        <input type="checkbox" bind:checked={r.pick} />
                        <span>{r.t.title}</span>
                        <span class="muted small">week of {fmtDay(r.week)} · {fwdInfo(r)}</span>
                      </label>
                      {#if fwdSaving === r.t.id}
                        <span class="muted small">Saving…</span>
                      {:else}
                        <button class="mini" disabled={!!fwdSaving} aria-label={`Put “${r.t.title}” back on this list`}
                                onclick={() => dropForward(r, false)}>Put back</button>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
          {/if}
        {/if}
        {#if !fwdCanDrop && !fwdLoading}
          <p class="muted small">To drop to-dos from this list, run <code>web/db/0056_todo_carry_skip.sql</code> in the Supabase SQL editor.</p>
        {/if}
        <div class="pick-actions">
          {#if fwdRows.some((r) => r.pick)}
            <button class="primary" disabled={!!fwdSaving} onclick={forwardPicked}>Carry {fwdRows.filter((r) => r.pick).length} forward</button>
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
            {#if e.project_id}
              <CvRelated project={projById.get(e.project_id)} projectId={e.project_id} milestoneId={e.milestone_id} entryId={e.id} />
            {/if}
            <CvForm entry={null}
                    preset={{ source_type: "entry", entry_id: e.id, project_id: e.project_id, milestone_id: e.milestone_id,
                              entry_date: e.started_at.slice(0, 10),
                              title: e.description ?? (e.project_id ? projById.get(e.project_id)?.name ?? "" : "") }}
                    onsaved={() => (panel = null)} oncancel={() => (cvOpen = false)} />
          </div>
        {:else}
          <div class="entry-more">
            <button class="cv-btn" onclick={() => (cvOpen = true)}>Add as CV achievement…</button>
            {#if e.project_id}
              <button class="cv-btn" title="Its project's actions in the Logbook (changes not saved here are left behind)"
                      onclick={() => toLogbook(e.project_id!, e.milestone_id)}>To Logbook ›</button>
            {/if}
          </div>
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
  .fwd li { display: flex; align-items: center; gap: 0.6rem; }
  .fwd button { flex-shrink: 0; }
  .fwd-acts { display: flex; gap: 0.3rem; flex-shrink: 0; }
  .fwd label { display: flex; flex: 1; min-width: 0; flex-wrap: wrap; align-items: baseline; gap: 0.45rem; font-size: 0.88rem; cursor: pointer; }
  .fwd input { width: auto; }
  .ms-groups { display: grid; gap: 0.4rem; max-height: 58vh; overflow-y: auto; padding-right: 0.2rem; }
  .ms-group { border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.3rem 0.6rem; }
  .ms-group summary { cursor: pointer; display: flex; gap: 0.6rem; align-items: baseline; flex-wrap: wrap; padding: 0.25rem 0; font-size: 0.9rem; }
  .ms-group summary .muted { font-size: 0.78rem; }
  .ms-project { margin: 0.3rem 0 0.5rem 0.4rem; }
  .ms-project-head { display: flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; font-weight: 600; color: var(--ink-soft); }
  .ms-pick { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.2rem; }
  .ms-pick li { display: grid; grid-template-columns: auto 1fr auto auto auto; gap: 0.6rem; align-items: center; padding: 0.4rem 0.3rem; border-bottom: 1px solid var(--rule); }
  .ms-pick li.off { opacity: 0.55; }
  .ms-pick li.done strong { text-decoration: line-through; color: var(--ink-soft); }
  .ms-goto { color: inherit; text-decoration: none; }
  .ms-goto:hover { text-decoration: underline; }
  .ms-done { font-size: 0.78rem; color: var(--accent); }
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
  .menu button.back { color: var(--ink-soft); border-bottom: 1px solid var(--rule); border-radius: 4px 4px 0 0; }
  .card { background: var(--paper); border-radius: 4px; padding: 0.35rem 0.45rem; font-size: 0.78rem; display: grid; gap: 0.1rem; border-left: 3px solid var(--accent); }
  .card.duty { border-left-color: var(--ink-soft); }
  .card.sortable { grid-template-columns: auto 1fr; column-gap: 0.2rem; align-items: start; }
  .card .grip { font-size: 0.8rem; padding: 0; line-height: 1.4; opacity: 0.45; }
  .card .grip:hover, .card .grip:focus-visible { opacity: 1; }
  .card.dragging { box-shadow: 0 2px 10px rgb(0 0 0 / 0.15); }
  .card.lit, .tidy-row.lit { animation: lit 2.5s ease-out; }
  @keyframes lit { 0%, 40% { box-shadow: 0 0 0 3px var(--accent); } 100% { box-shadow: 0 0 0 3px transparent; } }
  .has-agenda { font-size: 0.8em; }
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
  .entry-more { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .cv-add { margin-top: 1rem; border-top: 1px solid var(--rule); padding-top: 0.8rem; }
  .cv-add h3 { font-size: 0.92rem; font-family: var(--font-ui); }
  .add-day { margin-top: auto; display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.25rem; }
  .add-day button { font-size: 0.72rem; padding: 0.15rem; background: none; border: 1px dashed var(--rule); color: var(--ink-soft); }
  .tidy { display: grid; gap: 0.05rem; padding-top: 0.3rem; border-top: 1px dashed var(--rule); font-family: var(--font-ui); }
  .tidy-row { display: flex; align-items: flex-start; gap: 0.3rem; min-width: 0; }
  .tidy-row input[type="checkbox"] { width: auto; margin: 0.2rem 0 0; flex-shrink: 0; }
  .tidy-title {
    flex: 1; min-width: 0; text-align: left; background: none; border: none; padding: 0.1rem 0.15rem; border-radius: 3px;
    font-size: 0.74rem; line-height: 1.3; color: var(--ink); white-space: normal; overflow-wrap: anywhere;
    /* up to two lines, then … */
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden;
  }
  .tidy-title:hover { background: var(--paper); }
  .tidy-link { flex-shrink: 0; text-decoration: none; font-size: 0.72rem; line-height: 1.3; padding: 0.1rem 0.1rem; border-radius: 3px; opacity: 0.8; }
  .tidy-link:hover, .tidy-link:focus-visible { opacity: 1; background: var(--paper); }
  .tidy-row.done .tidy-title { text-decoration: line-through; color: var(--ink-soft); }
  .tidy-row { border-radius: 3px; border-left: 3px solid transparent; padding-left: 0.1rem; }
  /* a tidy-up: its own colour, with the word in the tooltip and the menu, not colour alone */
  .tidy-row.tidyup { border-left-color: var(--series-3); background: color-mix(in srgb, var(--series-3) 12%, transparent); }
  .tidy-row.dragging { background: var(--paper); box-shadow: 0 2px 10px rgb(0 0 0 / 0.15); }
  .tgrip {
    background: none; border: none; padding: 0 0.05rem; font-size: 0.72rem; line-height: 1.5; color: var(--ink-soft);
    cursor: grab; touch-action: none; user-select: none; opacity: 0.45; flex-shrink: 0;
  }
  .tgrip:hover, .tgrip:focus-visible { opacity: 1; }
  .tgrip:active { cursor: grabbing; }
  .tidy-input { flex: 1; min-width: 0; font-size: 0.74rem; padding: 0.1rem 0.3rem; }
  .tidy-add { background: none; border: 1px dashed transparent; color: var(--ink-soft); }
  .tidy-add:hover, .tidy-add:focus { border-color: var(--rule); background: var(--paper); color: var(--ink); }

  .cal-switch { display: inline-flex; margin: 0 0 0.6rem; border: 1px solid var(--rule); border-radius: var(--radius); overflow: hidden; font-family: var(--font-ui); }
  .cal-switch button { border: none; border-radius: 0; background: none; padding: 0.3rem 0.8rem; font-size: 0.82rem; color: var(--ink-soft); }
  .cal-switch button.on { background: var(--accent); color: var(--accent-ink); }
  /* repeating small tasks: the list's button, the ↻ on a task of a series, the dialogs */
  .repeat-open { margin: 0 0 0.6rem 0.5rem; padding: 0.3rem 0.7rem; font-family: var(--font-ui); font-size: 0.82rem; vertical-align: top; }
  .tidy-repeat { flex-shrink: 0; font-size: 0.72rem; line-height: 1.5; color: var(--ink-soft); }
  .tidy-follow {
    flex-shrink: 0; padding: 0 0.15rem; border: none; background: none; font-size: 0.72rem; line-height: 1.5;
    color: var(--ink-soft); cursor: pointer;
  }
  .tidy-follow:hover, .tidy-follow:focus-visible { color: var(--accent); }
  .repeat-ways { display: grid; gap: 0.35rem; margin: 0; padding: 0; border: none; }
  .repeat-ways label { display: flex; gap: 0.45rem; align-items: center; font-weight: normal; }
  .repeat-ways input { width: auto; margin: 0; }
  .repeat-list { list-style: none; margin: 0.4rem 0 0.8rem; padding: 0; display: grid; gap: 0.4rem; }
  .repeat-list li { display: flex; gap: 0.6rem; align-items: center; justify-content: space-between;
    padding-bottom: 0.4rem; border-bottom: 1px solid var(--rule); }
  .repeat-list .r-main { display: grid; gap: 0.1rem; min-width: 0; }
  .repeat-list.stopped li { color: var(--ink-soft); }
  .month-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
  .month .month-nav h2 { margin: 0; font-size: 1.1rem; min-width: 9.5rem; text-align: center; }
  .month-nav button:not(.link) { padding: 0.25rem 0.7rem; }
  .month-nav .link { background: none; border: none; padding: 0; color: var(--accent); cursor: pointer; font-family: var(--font-ui); font-size: 0.85rem; }
  /* the month scrolls in its own box; the weekday names stay on top */
  .month-scroll { max-height: calc(100vh - 12rem); min-height: 20rem; overflow-y: auto; border-radius: var(--radius); }
  .month-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 0.3rem; }
  .m-dow { position: sticky; top: 0; z-index: 1; background: var(--paper); font-family: var(--font-ui); font-size: 0.75rem; font-weight: 600; color: var(--ink-soft); padding: 0.25rem 0.3rem; }
  .m-cell { background: var(--panel); border-radius: var(--radius); padding: 0.35rem; min-height: 6.5rem; display: flex; flex-direction: column; gap: 0.2rem; min-width: 0; }
  .m-cell.out { opacity: 0.45; }
  .m-cell.today { outline: 2px solid var(--accent); }
  .m-cell .tidy { border-top: none; padding-top: 0; max-height: 9rem; overflow-y: auto; }
  .m-date { font-family: var(--font-ui); font-size: 0.78rem; font-weight: 600; color: var(--ink-soft); }
  .m-cell.today .m-date { color: var(--accent); }
  /* a phone: the month as a list of its days, opened at today */
  .month-list { display: grid; gap: 0.35rem; }
  .month-list .m-cell { min-height: 0; display: grid; grid-template-columns: 3.4rem minmax(0, 1fr); gap: 0.5rem; padding: 0.45rem 0.55rem; scroll-margin-top: 4.5rem; }
  .month-list .m-cell .tidy { max-height: none; overflow: visible; }
  .month-list .m-cell.empty { background: none; border-bottom: 1px solid var(--rule); border-radius: 0; }
  .month-list .m-date { font-weight: 400; padding-top: 0.15rem; }
  .month-list .m-date strong { font-size: 0.95rem; color: var(--ink); }
  @media (max-width: 48rem) {
    .tidy-title { font-size: 0.88rem; }
    .tidy-input { font-size: 0.88rem; padding: 0.3rem 0.4rem; }
    .tidy-row input[type="checkbox"] { width: 1.15rem; height: 1.15rem; }
    .tgrip { font-size: 1rem; padding: 0 0.15rem; opacity: 0.6; }
    .tidy-row { gap: 0.45rem; }
  }

  .week h2 { margin-top: 2rem; }
  .group { margin-top: 1rem; font-family: var(--font-ui); }
  .group h3 { font-size: 0.9rem; margin-bottom: 0.3rem; }
  .muted-group { opacity: 0.75; }
  .todos { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .todo-list :global(.grip) { margin-top: 0.55rem; }
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
  .inotes .link { background: none; border: none; padding: 0; font-size: 0.75rem; color: var(--danger); cursor: pointer; }
  .note-box { display: grid; gap: 0.3rem; width: 100%; max-width: 46rem; margin-top: 0.2rem; }
  .idea-title { font-size: 0.92rem; overflow-wrap: anywhere; }
  .editable { justify-self: start; cursor: text; }
  .idea.cancelled .idea-title { text-decoration: line-through; color: var(--ink-soft); }
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

  /* on a phone: Calendar | To-dos, and a strip of the week's days to pick one */
  .m-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem; padding: 0.2rem; margin: 0 0 0.8rem;
              background: var(--panel); border-radius: var(--radius); font-family: var(--font-ui); }
  .m-switch button { border: none; background: none; padding: 0.5rem; font-size: 0.95rem; color: var(--ink-soft); border-radius: var(--radius); }
  .m-switch button.on { background: var(--paper); color: var(--ink); font-weight: 600; box-shadow: 0 1px 2px rgb(0 0 0 / 0.12); }
  .m-count { margin-left: 0.35rem; font-size: 0.75rem; font-weight: 400; color: var(--ink-soft); }
  .m-days { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 0.2rem; margin: 0 0 0.5rem; font-family: var(--font-ui); }
  .m-days button { display: grid; justify-items: center; gap: 0.05rem; padding: 0.35rem 0; border: 1px solid var(--rule);
                   background: none; border-radius: var(--radius); color: var(--ink); }
  .m-days button.today { border-color: var(--accent); }
  .m-days button.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .m-dname { font-size: 0.7rem; }
  .m-days strong { font-size: 1rem; line-height: 1.1; }
  .m-dh { font-size: 0.65rem; opacity: 0.8; }

  @media (max-width: 60rem) {
    .days { grid-template-columns: 1fr; }
    .day { min-height: 0; }
    .todo { grid-template-columns: auto 1fr; }
    .t-acts { grid-column: 2; justify-content: flex-start; }
  }
</style>
