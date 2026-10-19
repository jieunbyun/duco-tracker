<script lang="ts">
  import { untrack } from "svelte";
  import { saveEntry, deleteEntry, saveProject, saveMilestone } from "./data";
  import type { Taxonomy, Project, TimeEntry, TimeEntryFields } from "./data";
  import { addDays } from "./dates";
  import { LIVE_STATUSES } from "./horizon";

  type Defaults = {
    date: string;
    start: string;
    end: string;
    categoryId: string;
    projectId?: string | null;
    milestoneId?: string | null;
    description?: string;
    isCore?: boolean;
  };
  type Props = {
    entry: TimeEntry | null; // null = a new entry
    tax: Taxonomy;
    projects: Project[];
    defaults: Defaults;
    /** what happened: a new entry, a change, a copy to another date, or a deletion */
    onsaved: (fields: TimeEntryFields, id: string, action: "created" | "updated" | "copied" | "deleted") => void;
    submitLabel?: string;
    oncancel?: () => void;
  };
  let { entry, tax, projects, defaults, onsaved, oncancel, submitLabel }: Props = $props();

  const NEW = "__new__";

  // ---- draft, copied once from the entry (or the defaults) ----------------
  // Timestamps hold wall-clock time labelled UTC, so the clock time is simply
  // the text after the "T".
  const init = untrack(() => ({ entry, defaults }));
  const e0 = init.entry;
  const endIsMidnight = !!e0?.ended_at && e0.ended_at.slice(11, 16) === "00:00" &&
                        e0.ended_at.slice(0, 10) > e0.started_at.slice(0, 10);

  let category_id = $state(e0?.category_id ?? init.defaults.categoryId);
  let projectPick = $state<string>(e0 ? e0.project_id ?? "" : init.defaults.projectId ?? "");
  let milestonePick = $state<string>(e0 ? e0.milestone_id ?? "" : init.defaults.milestoneId ?? "");
  let newProject = $state("");
  let newMilestone = $state("");
  let date = $state(e0 ? e0.started_at.slice(0, 10) : init.defaults.date);
  let mode = $state<"times" | "minutes">(e0 && !e0.ended_at ? "minutes" : "times");
  let start = $state(e0 ? e0.started_at.slice(11, 16) : init.defaults.start);
  let end = $state(e0?.ended_at ? (endIsMidnight ? "00:00" : e0.ended_at.slice(11, 16)) : init.defaults.end);
  let minutes = $state<number | null>(e0?.manual_minutes ?? 30);
  let description = $state(e0 ? e0.description ?? "" : init.defaults.description ?? "");
  let is_core = $state(e0 ? e0.is_core : init.defaults.isCore ?? false);
  let busy = $state(false);
  let error = $state("");
  let copyTo = $state(e0 ? e0.started_at.slice(0, 10) : "");

  // ---- choices -------------------------------------------------------------
  const groups = $derived(
    tax.areas.map((a) => ({ area: a, cats: tax.categories.filter((c) => c.area_id === a.id) })),
  );
  // Projects of the chosen category that are still live, plus the one this
  // entry already points at (so editing never hides the current value).
  const projectOptions = $derived(
    projects
      .filter((p) => p.category_id === category_id && (LIVE_STATUSES.has(p.status) || p.id === e0?.project_id))
      .sort((a, b) => a.name.localeCompare(b.name)),
  );
  const project = $derived(projects.find((p) => p.id === projectPick) ?? null);
  const categoryNote = $derived(tax.categories.find((c) => c.id === category_id)?.description ?? "");
  const milestoneOptions = $derived(
    (project?.milestone ?? []).filter((m) => (m.status !== "done" && m.status !== "dropped") || m.id === e0?.milestone_id),
  );

  function onCategory() {
    if (projectPick && projectPick !== NEW && !projectOptions.some((p) => p.id === projectPick)) projectPick = "";
    milestonePick = "";
  }
  function onProject() {
    milestonePick = "";
  }

  // ---- duration -------------------------------------------------------------
  /** started/ended for a day and two clock times; 00:00 as an end means midnight. */
  function stamps(day: string): { started_at: string; ended_at: string | null } | string {
    if (!start) return "Give a start time.";
    const started_at = `${day}T${start}:00+00:00`;
    if (mode === "minutes") return { started_at, ended_at: null };
    if (!end) return "Give an end time.";
    const ended_at = end === "00:00" ? `${addDays(day, 1)}T00:00:00+00:00` : `${day}T${end}:00+00:00`;
    if (ended_at <= started_at) return "End must be after start (use 00:00 for midnight).";
    return { started_at, ended_at };
  }

  const durationText = $derived.by(() => {
    if (mode === "minutes") return minutes ? `${Math.round((minutes / 60) * 100) / 100} h` : "";
    const s = stamps(date);
    if (typeof s === "string" || !s.ended_at) return "";
    const h = (Date.parse(s.ended_at) - Date.parse(s.started_at)) / 3_600_000;
    return `${Math.round(h * 100) / 100} h`;
  });

  // ---- save -------------------------------------------------------------------
  async function fields(day: string): Promise<TimeEntryFields | string> {
    const s = stamps(day);
    if (typeof s === "string") return s;
    if (mode === "minutes" && !(minutes && minutes > 0)) return "Give the minutes.";

    let project_id: string | null = projectPick || null;
    if (projectPick === NEW) {
      if (!newProject.trim()) return "Name the new project, or pick one.";
      project_id = await saveProject(null, {
        name: newProject.trim(), category_id, status: "active", start_on: day, end_on: null,
        planned_hours: null, is_important: false, notes: null,
      });
    }
    let milestone_id: string | null = project_id && milestonePick ? milestonePick : null;
    if (project_id && milestonePick === NEW) {
      if (!newMilestone.trim()) return "Name the new milestone, or pick one.";
      milestone_id = await saveMilestone(null, {
        project_id, title: newMilestone.trim(), status: "active", start_on: day, due_on: null,
        planned_hours: null, hard_deadline: false, sort_order: 100, notes: null,
      });
    }
    return {
      category_id,
      project_id,
      milestone_id,
      started_at: s.started_at,
      ended_at: s.ended_at,
      manual_minutes: mode === "minutes" ? Math.round(minutes!) : null,
      description: description.trim() || null,
      is_core,
    };
  }

  async function run(action: () => Promise<void>) {
    busy = true;
    error = "";
    try {
      await action();
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  function save(event: SubmitEvent) {
    event.preventDefault();
    run(async () => {
      const f = await fields(date);
      if (typeof f === "string") return void (error = f);
      const id = await saveEntry(e0?.id ?? null, f);
      onsaved(f, id, e0 ? "updated" : "created");
    });
  }

  function duplicate() {
    run(async () => {
      if (!copyTo) return void (error = "Pick a date to copy to.");
      const f = await fields(copyTo);
      if (typeof f === "string") return void (error = f);
      const id = await saveEntry(null, f);
      onsaved(f, id, "copied");
    });
  }

  function remove() {
    if (!e0 || !confirm("Delete this entry?")) return;
    run(async () => {
      await deleteEntry(e0.id);
      onsaved({ ...e0 }, e0.id, "deleted");
    });
  }
</script>

<form class="entry" onsubmit={save}>
  <label>
    Category
    <select bind:value={category_id} onchange={onCategory}>
      {#each groups as g (g.area.id)}
        <optgroup label={g.area.label}>
          {#each g.cats as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
        </optgroup>
      {/each}
    </select>
  </label>

  <label>
    Project
    <select bind:value={projectPick} onchange={onProject}>
      <option value="">— none —</option>
      {#each projectOptions as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
      <option value={NEW}>+ New project…</option>
    </select>
  </label>
  {#if categoryNote}<p class="hint">{categoryNote}</p>{/if}
  {#if projectPick === NEW}
    <label>New project name <input bind:value={newProject} placeholder="e.g. DAFNI Fellowship" /></label>
  {/if}

  {#if projectPick}
    <label>
      Milestone
      <select bind:value={milestonePick}>
        <option value="">— none —</option>
        {#each milestoneOptions as m (m.id)}<option value={m.id}>{m.title}</option>{/each}
        <option value={NEW}>+ New milestone…</option>
      </select>
    </label>
    {#if milestonePick === NEW}
      <label>New milestone name <input bind:value={newMilestone} placeholder="e.g. First draft" /></label>
    {/if}
  {/if}

  <div class="when">
    <label>Date <input type="date" bind:value={date} required /></label>
    <div class="mode" role="group" aria-label="Duration">
      <button type="button" class:on={mode === "times"} aria-pressed={mode === "times"} onclick={() => (mode = "times")}>Start & end</button>
      <button type="button" class:on={mode === "minutes"} aria-pressed={mode === "minutes"} onclick={() => (mode = "minutes")}>Minutes</button>
    </div>
    <label>Start <input type="time" bind:value={start} step="300" required /></label>
    {#if mode === "times"}
      <label>End <input type="time" bind:value={end} step="300" required /></label>
    {:else}
      <label>Minutes <input type="number" min="1" max="960" step="5" bind:value={minutes} /></label>
    {/if}
    <span class="duration muted">{durationText}</span>
  </div>

  <label class="wide">Note <input bind:value={description} placeholder="optional" /></label>
  <label class="check"><input type="checkbox" bind:checked={is_core} /> 🎯 Core session</label>

  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{submitLabel ?? (e0 ? "Save changes" : "Log session")}</button>
    {#if oncancel}<button type="button" onclick={oncancel} disabled={busy}>Cancel</button>{/if}
    {#if e0}
      <span class="copy">
        <input type="date" bind:value={copyTo} aria-label="Copy to date" />
        <button type="button" onclick={duplicate} disabled={busy}>Copy to date</button>
      </span>
      <button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>
    {/if}
  </div>
</form>

<style>
  .entry {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
    gap: 0.75rem 1rem;
    font-family: var(--font-ui);
  }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide, .when { grid-column: 1 / -1; }
  .hint { grid-column: 1 / -1; margin: -0.35rem 0 0; font-size: 0.8rem; color: var(--ink-soft); white-space: pre-line; }

  .when {
    display: grid;
    grid-template-columns: 10rem auto 8rem 8rem 1fr;
    gap: 0.75rem;
    align-items: end;
  }
  .mode { display: flex; }
  .mode button { font-size: 0.82rem; padding: 0.45rem 0.7rem; border-radius: 0; }
  .mode button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
  .mode button:last-child { border-radius: 0 var(--radius) var(--radius) 0; border-left: none; }
  .mode button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .duration { padding-bottom: 0.5rem; font-size: 0.85rem; }
  .check { display: flex; align-items: center; gap: 0.45rem; color: var(--ink); font-size: 0.9rem; }
  .check input { width: auto; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
  .copy { display: inline-flex; gap: 0.35rem; margin-left: auto; }
  .copy input { width: 10rem; }
  .danger { color: var(--danger); }
  @media (max-width: 40rem) {
    .when { grid-template-columns: 1fr 1fr; }
    .when > label:first-child, .mode, .duration { grid-column: 1 / -1; }
    .copy { margin-left: 0; }
  }
</style>
