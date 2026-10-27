<script lang="ts">
  import { untrack } from "svelte";
  import { PROJECT_STATUSES, saveProject, deleteProject } from "./data";
  import type { Category, Project } from "./data";
  import { plannedOf } from "./horizon";
  import { fmtHours } from "./data";

  type Props = {
    project: Project | null; // null = new project
    categories: { category: Category; areaLabel: string }[];
    categoryId: string;
    shared?: { id: string; title: string; taken: boolean }[]; // shared projects it can stand for (taken: by another of yours)
    onsaved: () => void;
    oncancel: () => void;
  };
  let { project, categories, categoryId, shared = [], onsaved, oncancel }: Props = $props();

  // A local draft, copied once when the editor opens: nothing reaches the
  // database until Save, and a reload behind it does not overwrite typing.
  const initial = untrack(() => project);
  let name = $state(initial?.name ?? "");
  let category_id = $state(initial?.category_id ?? untrack(() => categoryId));
  let status = $state(initial?.status ?? "planned");
  let start_on = $state(initial?.start_on ?? "");
  let end_on = $state(initial?.end_on ?? "");
  let planned = $state<number | null>(initial?.planned_hours ?? null);
  let is_important = $state(initial?.is_important ?? false);
  let notes = $state(initial?.notes ?? "");
  let folder = $state(initial?.folder_url ?? "");
  let groupProject = $state(initial?.group_project_id ?? "");
  let busy = $state(false);
  let error = $state("");

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (start_on && end_on && end_on < start_on) return (error = "The end date is before the start date.");
    busy = true;
    error = "";
    try {
      await saveProject(project?.id ?? null, {
        name: name.trim(),
        category_id,
        status,
        start_on: start_on || null,
        end_on: end_on || null,
        planned_hours: planned === null || Number.isNaN(planned) ? null : planned,
        is_important,
        notes: notes.trim() || null,
        folder_url: folder.trim() || null,
        // only sent when there is something to say, so saving works before 0040 is run
        ...(groupProject || initial?.group_project_id ? { group_project_id: groupProject || null } : {}),
      });
      onsaved();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!project) return;
    if (!confirm(`Delete “${project.name}” and its milestones? Logged time stays, without the project.`)) return;
    busy = true;
    try {
      await deleteProject(project.id);
      onsaved();
    } catch (e) {
      error = (e as Error).message;
      busy = false;
    }
  }
</script>

<form class="editor" onsubmit={save}>
  <label class="wide">Name <input bind:value={name} required /></label>
  <label>
    Category
    <select bind:value={category_id}>
      {#each categories as c (c.category.id)}
        <option value={c.category.id}>{c.areaLabel} · {c.category.label}</option>
      {/each}
    </select>
  </label>
  <label>
    Status
    <select bind:value={status}>
      {#each PROJECT_STATUSES as s (s)}<option value={s}>{s}</option>{/each}
    </select>
  </label>
  <label>Start <input type="date" bind:value={start_on} /></label>
  <label>End <input type="date" bind:value={end_on} min={start_on || undefined} /></label>
  <label>
    Planned hours <input type="number" min="0" step="0.5" bind:value={planned} />
    {#if project && plannedOf(project).fromMilestones}
      <span class="override">
        Using the milestones' total, {fmtHours(plannedOf(project).hours ?? 0)}{plannedOf(project).complete
          ? "; a figure here applies only if a milestone loses its hours."
          : " (only the milestones that have hours); enter a figure here to use it instead."}
      </span>
    {/if}
  </label>
  <label class="check"><input type="checkbox" bind:checked={is_important} /> Important</label>
  <label class="wide">Notes <textarea rows="3" bind:value={notes}></textarea></label>
  <label class="wide">OneDrive folder (link) <input type="url" bind:value={folder} placeholder="https://…sharepoint.com/…" /></label>
  {#if shared.length || groupProject}
    <label class="wide">
      Shared project
      <select bind:value={groupProject}>
        <option value="">— none —</option>
        {#each shared as s (s.id)}
          <option value={s.id} disabled={s.taken && s.id !== initial?.group_project_id}>{s.title}{s.taken && s.id !== initial?.group_project_id ? " (linked to another project)" : ""}</option>
        {/each}
      </select>
      <span class="hint">Its milestones come in here, and this project's go there as private ones (🔒, only you): one list,
        kept in step both ways. Planned hours are your hours there; only you see them.</span>
    </label>
  {/if}
  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy || !name.trim()}>{project ? "Save" : "Add project"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if project}<button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>{/if}
  </div>
</form>

<style>
  .editor {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
    gap: 0.75rem 1rem;
    font-family: var(--font-ui);
  }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .override { font-size: 0.75rem; color: var(--accent); }
  .hint { font-size: 0.75rem; }
  .check { display: flex; align-items: center; gap: 0.45rem; align-self: end; padding-bottom: 0.5rem; color: var(--ink); }
  .check input { width: auto; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
</style>
