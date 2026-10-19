<script lang="ts">
  import { untrack } from "svelte";
  import { saveTodo, deleteTodo, saveSlot } from "./data";
  import type { Taxonomy, Project, Todo, Slot, TodoFields } from "./data";
  import { addDays } from "./dates";
  import { LIVE_STATUSES } from "./horizon";

  type Props = {
    todo: Todo | null; // null = new
    slots: Slot[]; // this to-do's sittings (for a meeting: its one sitting)
    tax: Taxonomy;
    projects: Project[];
    weekStart: string;
    day?: string; // preset day for a new item
    placeOnDay?: boolean; // a new task is also planned onto `day`
    kind?: "task" | "meeting";
    /** what happened, and the ids of any to-dos created (for undo) */
    onsaved: (info: { action: "created" | "updated" | "deleted" | "cancelled" | "restored"; ids?: string[] }) => void;
    oncancel: () => void;
  };
  let { todo, slots, tax, projects, weekStart, day, placeOnDay, kind: kind0, onsaved, oncancel }: Props = $props();

  const init = untrack(() => ({ todo, slots, weekStart, day, kind0, placeOnDay }));
  const t0 = init.todo;
  const meetingSlot = t0?.kind === "meeting" ? init.slots[0] ?? null : null;

  let kind = $state<"task" | "meeting">(t0?.kind === "meeting" ? "meeting" : t0 ? "task" : init.kind0 ?? "task");
  let title = $state(t0?.title ?? "");
  let category_id = $state(t0?.category_id ?? "");
  let project_id = $state(t0?.project_id ?? "");
  let milestone_id = $state(t0?.milestone_id ?? "");
  let est = $state<number | null>(t0?.est_hours ?? null);
  let must = $state(t0?.must_this_week ?? false);
  let core = $state(t0?.is_core ?? false);
  let note = $state(t0?.note ?? "");
  let due_on = $state(t0?.due_on ?? init.day ?? init.weekStart);
  let date = $state(meetingSlot?.planned_on ?? t0?.due_on ?? init.day ?? init.weekStart);
  let start = $state(meetingSlot?.start_time?.slice(0, 5) ?? "10:00");
  let end = $state(meetingSlot?.end_time?.slice(0, 5) ?? "11:00");
  let repeat = $state(1);
  let busy = $state(false);
  let error = $state("");

  const groups = $derived(tax.areas.map((a) => ({
    area: a,
    cats: tax.allCategories.filter((c) => c.area_id === a.id && (c.is_active || c.id === t0?.category_id)),
  })));
  const projectOptions = $derived(
    projects
      .filter((p) => (!category_id || p.category_id === category_id) && (LIVE_STATUSES.has(p.status) || p.id === t0?.project_id))
      .sort((a, b) => a.name.localeCompare(b.name)),
  );
  const project = $derived(projects.find((p) => p.id === project_id) ?? null);
  const categoryNote = $derived(tax.categories.find((c) => c.id === category_id)?.description ?? "");
  const milestoneOptions = $derived(
    (project?.milestone ?? []).filter((m) => (m.status !== "done" && m.status !== "dropped") || m.id === t0?.milestone_id),
  );

  function onCategory() {
    if (project_id && !projectOptions.some((p) => p.id === project_id)) project_id = "";
    milestone_id = "";
  }
  function onProject() {
    // a project carries its own category
    if (project) category_id = project.category_id;
    milestone_id = "";
  }

  const hours = (a: string, b: string) => {
    const [ah, am] = a.split(":").map(Number);
    const [bh, bm] = b.split(":").map(Number);
    return Math.round(((bh * 60 + bm - ah * 60 - am) / 60) * 100) / 100;
  };

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!title.trim()) return (error = "Give it a title.");
    if (kind === "meeting" && !(start && end && end > start)) return (error = "The meeting must end after it starts.");
    busy = true;
    error = "";
    const created: string[] = [];
    try {
      const base: Partial<TodoFields> = {
        kind,
        title: title.trim(),
        category_id: category_id || null,
        project_id: project_id || null,
        milestone_id: milestone_id || null,
        is_core: core,
        note: note.trim() || null,
      };
      if (kind === "task") {
        const id = await saveTodo(t0?.id ?? null, { ...base, due_on, est_hours: est ?? null, must_this_week: must });
        created.push(id);
        if (!t0 && init.placeOnDay && init.day) {
          await saveSlot(null, { todo_id: id, planned_on: init.day, planned_hours: null });
        }
      } else {
        const len = hours(start, end);
        const times = { start_time: start, end_time: end, planned_hours: len };
        if (t0) {
          await saveTodo(t0.id, { ...base, due_on: date, est_hours: len });
          if (meetingSlot) await saveSlot(meetingSlot.id, { planned_on: date, ...times });
          else await saveSlot(null, { todo_id: t0.id, planned_on: date, ...times });
        } else {
          for (let i = 0; i < Math.max(1, repeat); i++) {
            const d = addDays(date, 7 * i);
            const id = await saveTodo(null, { ...base, due_on: d, est_hours: len, must_this_week: true });
            created.push(id);
            await saveSlot(null, { todo_id: id, planned_on: d, ...times });
          }
        }
      }
      onsaved(t0 ? { action: "updated" } : { action: "created", ids: created });
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!t0 || !confirm(`Delete “${t0.title}”${t0.kind === "task" ? " and its planned days" : ""}? Logged time stays.`)) return;
    busy = true;
    try {
      await deleteTodo(t0.id);
      onsaved({ action: "deleted" });
    } catch (err) {
      error = (err as Error).message;
      busy = false;
    }
  }

  async function toggleCancelled() {
    if (!t0) return;
    busy = true;
    try {
      await saveTodo(t0.id, { is_cancelled: !t0.is_cancelled });
      onsaved({ action: t0.is_cancelled ? "restored" : "cancelled" });
    } catch (err) {
      error = (err as Error).message;
      busy = false;
    }
  }
</script>

<form class="todo-form" onsubmit={save}>
  {#if !t0}
    <div class="kind wide" role="group" aria-label="Kind">
      <button type="button" class:on={kind === "task"} aria-pressed={kind === "task"} onclick={() => (kind = "task")}>Duty / to-do</button>
      <button type="button" class:on={kind === "meeting"} aria-pressed={kind === "meeting"} onclick={() => (kind = "meeting")}>Meeting</button>
    </div>
  {/if}

  <label class="wide">Title <input bind:value={title} placeholder={kind === "meeting" ? "e.g. DD weekly" : "e.g. Referee report for RESS"} /></label>

  <label>
    Category
    <select bind:value={category_id} onchange={onCategory}>
      <option value="">— none —</option>
      {#each groups as g (g.area.id)}
        <optgroup label={g.area.label}>
          {#each g.cats as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
        </optgroup>
      {/each}
    </select>
  </label>
  <label>
    Project
    <select bind:value={project_id} onchange={onProject}>
      <option value="">— none —</option>
      {#each projectOptions as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
    </select>
  </label>
  {#if categoryNote}<p class="hint">{categoryNote}</p>{/if}
  {#if project_id}
    <label>
      Milestone
      <select bind:value={milestone_id}>
        <option value="">— none —</option>
        {#each milestoneOptions as m (m.id)}<option value={m.id}>{m.title}</option>{/each}
      </select>
    </label>
  {/if}

  {#if kind === "task"}
    <label>Week of <input type="date" bind:value={due_on} required /></label>
    <label>Estimated hours <input type="number" min="0" step="0.5" bind:value={est} /></label>
    <label class="check"><input type="checkbox" bind:checked={must} /> Must do this week</label>
  {:else}
    <label>Date <input type="date" bind:value={date} required /></label>
    <label>Start <input type="time" step="300" bind:value={start} required /></label>
    <label>End <input type="time" step="300" bind:value={end} required /></label>
    {#if !t0}
      <label>Repeat weekly <select bind:value={repeat}>
        {#each [1, 2, 3, 4, 6, 8, 10, 12] as n (n)}<option value={n}>{n === 1 ? "no" : `${n} weeks`}</option>{/each}
      </select></label>
    {/if}
  {/if}
  <label class="check"><input type="checkbox" bind:checked={core} /> 🎯 Core</label>
  <label class="wide">Note <input bind:value={note} placeholder="optional" /></label>

  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{t0 ? "Save" : kind === "meeting" ? "Add meeting" : "Add to-do"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if t0}
      <button type="button" class="push" onclick={toggleCancelled} disabled={busy}>{t0.is_cancelled ? "Restore" : "Cancel this to-do"}</button>
      <button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>
    {/if}
  </div>
</form>

<style>
  .todo-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
    gap: 0.7rem 1rem;
    font-family: var(--font-ui);
  }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .hint { grid-column: 1 / -1; margin: -0.35rem 0 0; font-size: 0.8rem; color: var(--ink-soft); white-space: pre-line; }

  .kind { display: flex; }
  .kind button { font-size: 0.85rem; border-radius: 0; }
  .kind button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
  .kind button:last-child { border-radius: 0 var(--radius) var(--radius) 0; border-left: none; }
  .kind button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .check { display: flex; align-items: center; gap: 0.45rem; align-self: end; padding-bottom: 0.5rem; color: var(--ink); font-size: 0.88rem; }
  .check input { width: auto; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .push { margin-left: auto; }
  .danger { color: var(--danger); }
</style>
