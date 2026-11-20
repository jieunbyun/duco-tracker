<script lang="ts">
  // The CV records already on a logged session's project and milestone, shown above
  // the CV form so you can see whether this achievement is recorded already.
  import { untrack } from "svelte";
  import { loadCvFor } from "./data";
  import type { CvEntry, Project } from "./data";
  import { fmtDay } from "./dates";

  type Props = { project: Project | undefined; projectId: string; milestoneId: string | null; entryId: string };
  let { project, projectId, milestoneId, entryId }: Props = $props();

  let rows = $state<CvEntry[]>([]);
  let loading = $state(true);
  let error = $state("");

  untrack(() => loadCvFor(projectId, milestoneId))
    .then((r) => (rows = r))
    .catch((e) => (error = (e as Error).message))
    .finally(() => (loading = false));

  const milestoneTitle = (id: string | null) => (id ? project?.milestone.find((m) => m.id === id)?.title ?? null : null);
  const onMilestone = $derived(milestoneId ? rows.filter((r) => r.milestone_id === milestoneId) : []);
  const elsewhere = $derived(milestoneId ? rows.filter((r) => r.milestone_id !== milestoneId) : rows);
  const details = (r: CvEntry) => [r.description, r.outcome, r.metrics].map((v) => v?.trim()).filter(Boolean) as string[];
</script>

{#snippet list(items: CvEntry[], showMilestone: boolean)}
  <ul>
    {#each items as r (r.id)}
      {@const more = details(r)}
      {@const ms = showMilestone ? milestoneTitle(r.milestone_id) : null}
      <li>
        <details>
          <summary class:plain={!more.length}>
            <span class="date muted">{fmtDay(r.entry_date)}</span>
            <span class="what">
              <strong>{r.title}</strong>
              {#if r.entry_id === entryId}<small class="tag">from this session</small>{/if}
              <span class="sub muted">
                {r.cv_section}{r.cv_subsection ? ` › ${r.cv_subsection}` : ""}{ms ? ` · ${ms}` : ""}
              </span>
            </span>
            <span class="chip status-{r.status}">{r.status.replaceAll("_", " ")}</span>
          </summary>
          {#each more as m, i (i)}<p class="more">{m}</p>{/each}
        </details>
      </li>
    {/each}
  </ul>
{/snippet}

<div class="related">
  {#if loading}
    <p class="muted">Looking for CV records on this project…</p>
  {:else if error}
    <p class="error">Could not load the CV records already here: {error}</p>
  {:else if !rows.length}
    <p class="muted">No CV records on {project ? `“${project.name}”` : "this project"} yet.</p>
  {:else}
    <p class="lead">Already in your CV records — check this one isn't among them:</p>
    {#if milestoneId}
      <h4>This milestone{milestoneTitle(milestoneId) ? ` — ${milestoneTitle(milestoneId)}` : ""}
        <span class="muted">({onMilestone.length})</span></h4>
      {#if onMilestone.length}{@render list(onMilestone, false)}{:else}<p class="muted none">None yet.</p>{/if}
      {#if elsewhere.length}
        <h4>Elsewhere in {project ? `“${project.name}”` : "the project"} <span class="muted">({elsewhere.length})</span></h4>
        {@render list(elsewhere, true)}
      {/if}
    {:else}
      <h4>{project ? `“${project.name}”` : "This project"} <span class="muted">({rows.length})</span></h4>
      {@render list(rows, true)}
    {/if}
  {/if}
</div>

<style>
  .related {
    font-family: var(--font-ui); font-size: 0.85rem; background: var(--panel); border-radius: var(--radius);
    padding: 0.6rem 0.8rem; margin: 0.4rem 0 0.9rem; max-height: 16rem; overflow-y: auto;
  }
  .related p { margin: 0; }
  .lead { margin-bottom: 0.3rem !important; }
  h4 { margin: 0.5rem 0 0.2rem; font-size: 0.8rem; font-weight: 600; }
  h4:first-of-type { margin-top: 0.2rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  summary {
    display: grid; grid-template-columns: 5.5rem 1fr auto; gap: 0.6rem; align-items: baseline;
    padding: 0.25rem 0.3rem; border-radius: 4px; cursor: pointer; list-style: none;
  }
  summary::-webkit-details-marker { display: none; }
  summary.plain { cursor: default; }
  summary:hover { background: var(--paper); }
  .date { font-size: 0.78rem; }
  .sub { display: block; font-size: 0.76rem; }
  .tag { margin-left: 0.3rem; font-size: 0.7rem; color: var(--accent); }
  .chip { font-size: 0.7rem; }
  .more { padding: 0.1rem 0.3rem 0.2rem 6.4rem; white-space: pre-wrap; color: var(--ink-soft); font-size: 0.8rem; }
  .none { font-size: 0.8rem; }
  @media (max-width: 40rem) {
    summary { grid-template-columns: 1fr auto; }
    .date { grid-column: 1 / -1; }
    .more { padding-left: 0.3rem; }
  }
</style>
