<script lang="ts">
  import { MILESTONE_STATUSES, saveMilestone, deleteMilestone, fmtHours } from "./data";
  import type { Milestone, Project } from "./data";
  import { fmtDay } from "./dates";
  import { plannedOf } from "./horizon";

  type Props = { project: Project; actualByMilestone: Map<string, number>; onchange: () => void };
  let { project, actualByMilestone, onchange }: Props = $props();

  // Which row is open for editing: a milestone id, "new", or nothing.
  let editing = $state<string | null>(null);
  let draft = $state(blank());
  let busy = $state(false);
  let error = $state("");

  function blank() {
    return { title: "", status: "planned", start_on: "", due_on: "", planned: null as number | null, hard_deadline: false, notes: "" };
  }

  function open(m: Milestone | null) {
    error = "";
    editing = m?.id ?? "new";
    draft = m
      ? { title: m.title, status: m.status, start_on: m.start_on ?? "", due_on: m.due_on ?? "",
          planned: m.planned_hours, hard_deadline: m.hard_deadline, notes: m.notes ?? "" }
      : blank();
  }

  async function save(event: SubmitEvent, m: Milestone | null) {
    event.preventDefault();
    if (draft.start_on && draft.due_on && draft.due_on < draft.start_on) return (error = "The due date is before the start date.");
    busy = true;
    error = "";
    try {
      await saveMilestone(m?.id ?? null, {
        project_id: project.id,
        title: draft.title.trim(),
        status: draft.status,
        start_on: draft.start_on || null,
        due_on: draft.due_on || null,
        planned_hours: draft.planned === null || Number.isNaN(draft.planned) ? null : draft.planned,
        hard_deadline: draft.hard_deadline,
        sort_order: m?.sort_order ?? (project.milestone.length + 1) * 10,
        notes: draft.notes.trim() || null,
      });
      editing = null;
      onchange();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  async function remove(m: Milestone) {
    if (!confirm(`Delete milestone “${m.title}”? Logged time stays on the project.`)) return;
    busy = true;
    try {
      await deleteMilestone(m.id);
      editing = null;
      onchange();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  const plannedSum = $derived(project.milestone.reduce((s, m) => s + (m.planned_hours ?? 0), 0));
</script>

{#snippet form(m: Milestone | null)}
  <form class="ms-form" onsubmit={(e) => save(e, m)}>
    <label class="wide">Title <input bind:value={draft.title} required /></label>
    <label>
      Status
      <select bind:value={draft.status}>
        {#each MILESTONE_STATUSES as s (s)}<option value={s}>{s}</option>{/each}
      </select>
    </label>
    <label>Start <input type="date" bind:value={draft.start_on} /></label>
    <label>Due <input type="date" bind:value={draft.due_on} min={draft.start_on || undefined} /></label>
    <label>Planned hours <input type="number" min="0" step="0.5" bind:value={draft.planned} /></label>
    <label class="check"><input type="checkbox" bind:checked={draft.hard_deadline} /> Hard deadline</label>
    <label class="wide">Notes <textarea rows="2" bind:value={draft.notes}></textarea></label>
    {#if error}<p class="error wide">{error}</p>{/if}
    <div class="actions wide">
      <button class="primary" type="submit" disabled={busy || !draft.title.trim()}>{m ? "Save" : "Add milestone"}</button>
      <button type="button" onclick={() => (editing = null)} disabled={busy}>Cancel</button>
      {#if m}<button type="button" class="danger" onclick={() => remove(m)} disabled={busy}>Delete</button>{/if}
    </div>
  </form>
{/snippet}

<div class="milestones">
  <div class="head">
    <h3>Milestones</h3>
    {#if plannedOf(project).fromMilestones}
      <span class="muted">{fmtHours(plannedSum)} across the milestones — used as the project's plan</span>
    {:else if plannedSum > 0}
      <span class="muted">
        {fmtHours(plannedSum)}{project.planned_hours !== null ? ` of ${fmtHours(project.planned_hours)}` : ""} assigned so far;
        give every milestone hours to use their total as the plan
      </span>
    {/if}
  </div>

  {#if project.milestone.length}
    <ul>
      {#each project.milestone as m (m.id)}
        <li>
          {#if editing === m.id}
            {@render form(m)}
          {:else}
            {@const actual = actualByMilestone.get(m.id) ?? 0}
            <button class="ms-row" onclick={() => open(m)}>
              <span class="title">
                {m.title}
                {#if m.hard_deadline}<small class="hard">hard deadline</small>{/if}
              </span>
              <span class="chip status-{m.status}">{m.status}</span>
              <span class="dates muted">
                {m.start_on ? fmtDay(m.start_on) : "…"} – {m.due_on ? fmtDay(m.due_on) : "…"}
              </span>
              <span class="hours">
                <strong>{fmtHours(actual)}</strong>
                {#if m.planned_hours !== null}<span class="muted"> of {fmtHours(m.planned_hours)}</span>{/if}
              </span>
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {:else}
    <p class="muted empty">No milestones yet.</p>
  {/if}

  {#if editing === "new"}
    {@render form(null)}
  {:else}
    <button class="add" onclick={() => open(null)}>+ Milestone</button>
  {/if}
</div>

<style>
  .milestones { margin-top: 1.25rem; font-family: var(--font-ui); }
  .head { display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap; }
  .head .muted { font-size: 0.8rem; }
  h3 { font-size: 0.95rem; margin: 0 0 0.4rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .ms-row {
    width: 100%;
    display: grid;
    grid-template-columns: 1fr auto 13rem 8rem;
    gap: 0.75rem;
    align-items: center;
    text-align: left;
    background: none;
    border: none;
    padding: 0.45rem 0.4rem;
    font-size: 0.88rem;
  }
  .ms-row:hover { background: var(--paper); }
  .title small.hard { margin-left: 0.4rem; color: var(--danger); font-size: 0.72rem; }
  .dates { font-size: 0.8rem; }
  .hours { text-align: right; font-variant-numeric: tabular-nums; }
  .empty { font-size: 0.85rem; margin: 0.2rem 0 0.5rem; }
  .add { margin-top: 0.5rem; font-size: 0.85rem; }
  .ms-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
    gap: 0.6rem 0.9rem;
    background: var(--paper);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: 0.8rem;
    margin: 0.4rem 0;
  }
  label { display: grid; gap: 0.2rem; font-size: 0.8rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .check { display: flex; align-items: center; gap: 0.45rem; align-self: end; padding-bottom: 0.5rem; color: var(--ink); }
  .check input { width: auto; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
  @media (max-width: 40rem) {
    .ms-row { grid-template-columns: 1fr auto; }
    .dates { grid-column: 1; }
  }
</style>
