<script lang="ts">
  import {
    loadTaxonomy, loadProjects, loadWeekPlan, loadEntriesBetween, saveSlot, deleteSlot, saveTodo, deleteTodo, fmtHours,
  } from "../lib/data";
  import type { Taxonomy, Project, Todo, Slot, TimeEntry, TimeEntryFields } from "../lib/data";
  import { addDays, today, weekStart, parse, fmtDay } from "../lib/dates";
  import { meetingsInRange } from "../lib/ics";
  import type { Meeting } from "../lib/ics";
  import EntryForm from "../lib/EntryForm.svelte";
  import TodoForm from "../lib/TodoForm.svelte";
  import CvForm from "../lib/CvForm.svelte";

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

  async function load() {
    const id = ++request;
    const [from, to, carry] = [start, end, isCurrent];
    loading = true;
    try {
      const [plan, logged, p] = await Promise.all([
        loadWeekPlan(from, to, carry), loadEntriesBetween(from, to), loadProjects(),
      ]);
      if (id !== request) return;
      projects = p;
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
  const groups = $derived([
    { key: "must", title: "Must do this week", rows: live.filter((t) => !t.is_done && t.must_this_week && !carried.has(t.id)) },
    { key: "flex", title: "Flexible", rows: live.filter((t) => !t.is_done && !t.must_this_week && !carried.has(t.id)) },
    { key: "carried", title: "Carried over from earlier weeks", rows: live.filter((t) => !t.is_done && carried.has(t.id)) },
    { key: "done", title: "Done", rows: live.filter((t) => t.is_done) },
  ].map((g) => ({ ...g, rows: [...g.rows].sort((a, b) => a.sort_order - b.sort_order || a.title.localeCompare(b.title)) })));
  const cancelled = $derived(tasks.filter((t) => t.is_cancelled));

  function slotsOf(t: Todo): Slot[] {
    return slots.filter((s) => s.todo_id === t.id).sort((a, b) => a.planned_on.localeCompare(b.planned_on));
  }
  function loggedFor(t: Todo): number {
    return slotsOf(t).reduce((s, x) => s + ((x.entry_id && entryById.get(x.entry_id)?.minutes) || 0) / 60, 0);
  }

  // ---- summary ----------------------------------------------------------------------
  const summary = $derived.by(() => {
    const meetingH = weekSlots
      .filter((s) => todoById.get(s.todo_id)?.kind === "meeting" && !s.is_cancelled)
      .reduce((s, x) => s + (x.planned_hours ?? 0), 0);
    const open = live.filter((t) => !t.is_done);
    const dutyH = open.reduce((s, t) => s + (t.est_hours ?? 0), 0);
    const must = live.filter((t) => t.must_this_week && !carried.has(t.id));
    const logged = entries.reduce((s, e) => s + e.minutes / 60, 0);
    return { meetingH, dutyH, logged, mustDone: must.filter((t) => t.is_done).length, mustAll: must.length };
  });

  // ---- actions ------------------------------------------------------------------------
  const placeOn = (t: Todo, day: string) => act(() => saveSlot(null, { todo_id: t.id, planned_on: day, planned_hours: null }));
  const move = (s: Slot, by: number) => act(() => saveSlot(s.id, { planned_on: addDays(s.planned_on, by) }));
  function unplan(s: Slot) {
    const t = todoById.get(s.todo_id);
    if (t?.kind === "meeting") {
      if (!confirm(`Delete the meeting “${t.title}”?${s.entry_id ? " Its logged time stays." : ""} (Use Edit to change its time.)`)) return;
      return act(() => deleteTodo(t.id));
    }
    if (s.entry_id && !confirm("This day was logged. Remove it from the plan? The logged time stays.")) return;
    return act(() => deleteSlot(s.id));
  }
  // Cancelling keeps the card on its day, struck through, so the week still
  // shows what was planned; it can be restored. ✕ takes it off altogether.
  const setCancelled = (s: Slot, cancelled: boolean) => act(() => saveSlot(s.id, { is_cancelled: cancelled }));
  const setDone = (t: Todo, done: boolean) => act(() => saveTodo(t.id, { is_done: done, done_at: done ? new Date().toISOString() : null } as Partial<Todo>));
  const setMust = (t: Todo) => act(() => saveTodo(t.id, { must_this_week: !t.must_this_week }));
  const restore = (t: Todo) => act(() => saveTodo(t.id, { is_cancelled: false }));

  // ---- card menu: click or right-click a card ------------------------------------------
  // The cards stay quiet (title, tick, status); their actions live in one menu.
  type Menu = { slot: Slot; day: string; x: number; y: number };
  type Item = { label: string; run: () => unknown; danger?: boolean };
  let menu = $state<Menu | null>(null);
  const MENU_W = 220;
  const MENU_H = 250;

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
    const edit: Item = { label: meeting ? "Edit meeting" : "Edit to-do", run: () => (panel = { kind: "todo", todo: t }) };
    const remove: Item = meeting
      ? { label: "Delete meeting", run: () => unplan(s), danger: true }
      : { label: "Take off the calendar", run: () => unplan(s), danger: true };
    if (s.is_cancelled) return [{ label: "Restore", run: () => setCancelled(s, false) }, edit, remove];
    if (s.entry_id) {
      const e = entryById.get(s.entry_id);
      return [...(e ? [{ label: "Open logged entry", run: () => openEntry(e, m.day) }] : []), edit, remove];
    }
    const moves: Item[] = meeting
      ? []
      : [
          { label: "‹ Move to the day before", run: () => move(s, -1) },
          { label: "Move to the day after ›", run: () => move(s, 1) },
        ];
    return [
      { label: "✓ Log time", run: () => openLog(t, s, m.day) },
      ...moves,
      { label: meeting ? "Cancel meeting (keep, struck through)" : "Cancel this day (keep, struck through)", run: () => setCancelled(s, true) },
      edit,
      remove,
    ];
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
    | { kind: "entry"; entry: TimeEntry | null; day: string };
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

  async function entrySaved(f: TimeEntryFields) {
    try { localStorage.setItem(LAST_CATEGORY, f.category_id); } catch {}
    panel = null;
    await load();
  }

  async function logged(p: Extract<Panel, { kind: "log" }>, f: TimeEntryFields, entryId: string) {
    try {
      const day = f.started_at.slice(0, 10);
      if (p.slot) await saveSlot(p.slot.id, { entry_id: entryId, planned_on: day });
      else await saveSlot(null, { todo_id: p.todo.id, planned_on: day, entry_id: entryId });
      if (markDone) await saveTodo(p.todo.id, { is_done: true, done_at: new Date().toISOString() } as Partial<Todo>);
      try { localStorage.setItem(LAST_CATEGORY, f.category_id); } catch {}
    } catch (e) {
      error = (e as Error).message;
    }
    panel = null;
    await load();
  }

  async function closed() {
    panel = null;
    await load();
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
    try {
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
      importNote = `Added ${picked.length} ${picked.length === 1 ? "meeting" : "meetings"}.`;
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
  </p>

  <div class="toolbar">
    <button class="primary" onclick={() => openEntry(null, isCurrent ? today() : start)}>+ Log</button>
    <button onclick={() => (panel = { kind: "todo", todo: null, as: "task" })}>+ To-do</button>
    <button onclick={() => (panel = { kind: "todo", todo: null, as: "meeting", day: isCurrent ? today() : start })}>+ Meeting</button>
    <label class="toggle"><input type="checkbox" bind:checked={showLogged} /> Show logged time</label>
  </div>

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
          <div class="card meeting" class:logged={!!s.entry_id} class:cancelled={s.is_cancelled}
               role="group" oncontextmenu={(ev) => openMenu(ev, s, d)}>
            <button class="card-body" aria-haspopup="menu" title="Actions (click or right-click)"
                    onclick={(ev) => openMenu(ev, s, d)}>
              <span class="time">{hhmm(s.start_time)}–{hhmm(s.end_time)}</span>
              <span class="title">{t.is_core ? "🎯 " : ""}{t.title}</span>
              {#if label(t)}<span class="sub">{label(t)}</span>{/if}
              {#if s.is_cancelled}<span class="off">cancelled</span>{:else if s.entry_id}<span class="ok">✓ logged</span>{/if}
            </button>
          </div>
        {/each}

        {#each duties as s (s.id)}
          {@const t = todoById.get(s.todo_id)!}
          {@const e = s.entry_id ? entryById.get(s.entry_id) : null}
          <div class="card duty" class:logged={!!s.entry_id} class:done={t.is_done}
               class:cancelled={s.is_cancelled}
               class:stale={!s.entry_id && !s.is_cancelled && !t.is_done && d < today()}
               role="group" oncontextmenu={(ev) => openMenu(ev, s, d)}>
            <div class="duty-row">
              <input type="checkbox" checked={t.is_done} title={t.is_done ? "Done — untick to reopen" : "Mark the to-do done"}
                     aria-label={`${t.title} done`} onchange={(ev) => setDone(t, (ev.target as HTMLInputElement).checked)} />
              <button class="card-body" aria-haspopup="menu" title="Actions (click or right-click)"
                      onclick={(ev) => openMenu(ev, s, d)}>
                <span class="title">{t.must_this_week ? "● " : ""}{t.is_core ? "🎯 " : ""}{t.title}</span>
                {#if label(t)}<span class="sub">{label(t)}</span>{/if}
                {#if s.is_cancelled}<span class="off">cancelled</span>{:else if s.entry_id}<span class="ok">✓ {e ? fmtHours(e.minutes / 60) : "logged"}</span>{/if}
              </button>
            </div>
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

  <!-- ================= to-do list ================= -->
  <h2>To-dos</h2>
  {#if !tasks.length}
    <p class="muted">No to-dos for this week yet.</p>
  {/if}
  {#each groups as g (g.key)}
    {#if g.rows.length}
      <div class="group" class:muted-group={g.key === "done"}>
        <h3>{g.title} <span class="muted small">{g.rows.length}</span></h3>
        <ul class="todos">
          {#each g.rows as t (t.id)}
            {@const ts = slotsOf(t)}
            {@const lh = loggedFor(t)}
            <li class="todo">
              <input type="checkbox" checked={t.is_done} aria-label="Done" onchange={(ev) => setDone(t, (ev.target as HTMLInputElement).checked)} />
              <div class="t-main">
                <button class="t-title" onclick={() => (panel = { kind: "todo", todo: t })}>
                  {t.is_core ? "🎯 " : ""}{t.title}
                </button>
                <span class="t-meta muted">
                  {label(t)}{label(t) && (t.est_hours || lh) ? " · " : ""}
                  {#if lh}{fmtHours(lh)}{t.est_hours ? ` of ${fmtHours(t.est_hours)}` : ""} logged{:else if t.est_hours}est. {fmtHours(t.est_hours)}{/if}
                  {#if g.key === "carried"} · from week of {fmtDay(weekStart(t.due_on))}{/if}
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
                {#if !t.is_done}
                  <select aria-label="Plan on a day" onchange={(ev) => { const el = ev.target as HTMLSelectElement; if (el.value) placeOn(t, el.value); el.value = ""; }}>
                    <option value="">Plan on…</option>
                    {#each days as d (d)}<option value={d}>{dayName(d)} {dayNum(d)}</option>{/each}
                  </select>
                  <button class="mini" onclick={() => openLog(t, null, isCurrent ? today() : start)}>✓ Log</button>
                  <button class="mini" title={t.must_this_week ? "Make flexible" : "Make a must-do"} onclick={() => setMust(t)}>{t.must_this_week ? "→ flexible" : "→ must"}</button>
                {/if}
              </div>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  {/each}
  {#if cancelled.length}
    <details class="group">
      <summary class="muted small">Cancelled ({cancelled.length})</summary>
      <ul class="todos">
        {#each cancelled as t (t.id)}
          <li class="todo cancelled">
            <span class="t-title-static">{t.title}</span>
            <button class="mini" onclick={() => restore(t)}>Restore</button>
          </li>
        {/each}
      </ul>
    </details>
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

<svelte:window onkeydown={menuKeys} onresize={closeMenu} onscroll={closeMenu} />

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
    {:else if panel.kind === "entry"}
      {@const p = panel}
      <h2>{p.entry ? "Edit entry" : "Log time"}</h2>
      {#key p}
        <EntryForm entry={p.entry} {tax} {projects} defaults={entryDefaults(p.day)}
                   onsaved={(f) => entrySaved(f)} oncancel={() => (panel = null)} />
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
  .duty-row { display: flex; align-items: flex-start; gap: 0.3rem; }
  .duty-row input { width: auto; margin: 0.12rem 0 0; flex: none; }
  .menu-backdrop { position: fixed; inset: 0; z-index: 50; }
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
  .cancelled .t-title-static { text-decoration: line-through; color: var(--ink-soft); font-size: 0.88rem; }
  .todo.cancelled { grid-template-columns: 1fr auto; }

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
