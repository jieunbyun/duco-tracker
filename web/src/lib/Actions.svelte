<script lang="ts">
  // Action items in the Logbook: tick them off, add the next ones, each with a
  // note and links. They are to-dos, so they are on Week's list too.
  import { addAction, saveAction, setActionDone, deleteAction } from "./actions";
  import type { Action } from "./actions";
  import { parseLinks, linkName, planningGroups } from "./group";
  import type { GroupProject, PlanningRef } from "./group";

  type Props = {
    actions: Action[];
    projects: GroupProject[]; // shared projects
    planning?: PlanningRef[]; // your Planning projects, with milestones
    filter: string; // the project in view: "g:<id>", "p:<id>", or "" for all
    canWrite: boolean;
    onchanged: () => Promise<void>;
  };
  let { actions, projects, planning = [], filter, canWrite, onchanged }: Props = $props();

  let error = $state("");
  const act = async (f: () => Promise<unknown>) => {
    try { error = ""; await f(); await onchanged(); } catch (e) { error = (e as Error).message; }
  };
  const keyOf = (a: Action) => (a.project_id ? `p:${a.project_id}` : a.group_project_id ? `g:${a.group_project_id}` : "");
  const inView = $derived(actions.filter((a) => !filter || keyOf(a) === filter));
  const open = $derived(inView.filter((a) => !a.is_done));
  const done = $derived(inView.filter((a) => a.is_done).sort((a, b) => (b.done_at ?? "").localeCompare(a.done_at ?? "")));
  function where(a: Action): string {
    if (a.project_id) {
      const p = planning.find((x) => x.id === a.project_id);
      const m = p?.milestones.find((x) => x.id === a.milestone_id);
      return `${p?.name ?? "Planning project"}${m ? ` › ${m.title}` : ""}`;
    }
    return projects.find((x) => x.id === a.group_project_id)?.title ?? "Shared project";
  }

  // ---- a new action item, or one being edited ----------------------------------------
  type Draft = { id: string | null; title: string; project: string; milestone: string; note: string; links: string };
  const fresh = (): Draft => ({
    id: null, title: "", note: "", links: "", milestone: "",
    project: filter || (projects[0] ? `g:${projects[0].id}` : planning[0] ? `p:${planning[0].id}` : ""),
  });
  let draft = $state<Draft | null>(null);
  const activeMilestones = (key: string) =>
    key.startsWith("p:") ? (planning.find((p) => p.id === key.slice(2))?.milestones ?? []).filter((m) => m.active !== false) : [];
  async function submit(ev: SubmitEvent) {
    ev.preventDefault();
    const d = draft;
    if (!d || !d.title.trim()) return;
    if (!d.id && !d.project) return void (error = "Choose the project it belongs to.");
    const common = { title: d.title.trim(), note: d.note.trim() || null, links: parseLinks(d.links) };
    await act(() => d.id
      ? saveAction(d.id, common)
      : addAction({
          ...common,
          project_id: d.project.startsWith("p:") ? d.project.slice(2) : null,
          milestone_id: d.project.startsWith("p:") ? d.milestone || null : null,
          group_project_id: d.project.startsWith("g:") ? d.project.slice(2) : null,
        }));
    draft = d.id ? null : { ...fresh(), project: d.project, milestone: d.milestone }; // ready for the next one
  }
  function edit(a: Action) {
    draft = { id: a.id, title: a.title, project: keyOf(a), milestone: a.milestone_id ?? "", note: a.note ?? "", links: a.links.join("\n") };
  }
</script>

<section class="actions-box">
  <header>
    <h2>Action items <span class="muted">{open.length}</span></h2>
    <span class="muted small">They are to-dos too: they show on Week's list until done.</span>
    <span class="spacer"></span>
    {#if canWrite && !draft}<button class="mini" onclick={() => (draft = fresh())}>+ Action item</button>{/if}
  </header>
  {#if error}<p class="error">{error}</p>{/if}

  {#snippet editor()}
    {#if draft}
      <form class="a-form" onsubmit={submit}>
        <input class="a-title" bind:value={draft.title} placeholder="What needs doing" aria-label="Action item" required />
        {#if !draft.id}
          <select bind:value={draft.project} onchange={() => draft && (draft.milestone = "")} aria-label="Project">
            <option value="">Project…</option>
            {#if projects.length}
              <optgroup label="Shared projects">{#each projects as p (p.id)}<option value={`g:${p.id}`}>{p.title}</option>{/each}</optgroup>
            {/if}
            {#each planningGroups(planning) as g (g.label)}
              <optgroup label={g.label}>{#each g.items as p (p.id)}<option value={`p:${p.id}`}>{p.name}</option>{/each}</optgroup>
            {/each}
          </select>
          {#if activeMilestones(draft.project).length}
            <select bind:value={draft.milestone} aria-label="Milestone">
              <option value="">Milestone…</option>
              {#each activeMilestones(draft.project) as m (m.id)}<option value={m.id}>{m.title}</option>{/each}
            </select>
          {/if}
        {/if}
        <textarea rows="2" bind:value={draft.note} placeholder="Note (optional)" aria-label="Note"></textarea>
        <textarea rows="1" bind:value={draft.links} placeholder="Links, one per line (optional)" aria-label="Links"></textarea>
        <div class="a-acts">
          <button class="primary mini" type="submit">{draft.id ? "Save" : "Add"}</button>
          <button class="mini" type="button" onclick={() => (draft = null)}>{draft.id ? "Cancel" : "Done adding"}</button>
        </div>
      </form>
    {/if}
  {/snippet}
  {#if draft && !draft.id}{@render editor()}{/if}

  <ul class="a-list">
    {#each open as a (a.id)}
      <li>
        {#if draft?.id === a.id}
          {@render editor()}
        {:else}
          <label class="a-row">
            <input type="checkbox" checked={false} disabled={!canWrite} onchange={() => act(() => setActionDone(a.id, true))} aria-label={`Done: ${a.title}`} />
            <span class="a-text">
              <span class="a-name">{a.title}</span>
              {#if !filter}<span class="muted small"> · {where(a)}</span>{/if}
            </span>
          </label>
          {#if canWrite}
            <button class="link" onclick={() => edit(a)}>edit</button>
            <button class="x" title="Delete this action" aria-label={`Delete ${a.title}`}
                    onclick={() => confirm(`Delete “${a.title}”? It is a to-do, so it goes from Week too.`) && act(() => deleteAction(a.id))}>✕</button>
          {/if}
          {#if a.note}<p class="a-note">{a.note}</p>{/if}
          {#if a.links.length}
            <div class="a-links">{#each a.links as l (l)}<a href={l} target="_blank" rel="noopener noreferrer" title={l}>↗ {linkName(l)}</a>{/each}</div>
          {/if}
        {/if}
      </li>
    {:else}
      <li class="muted small">Nothing open{filter ? " for this project" : ""}.</li>
    {/each}
  </ul>

  {#if done.length}
    <details class="a-done">
      <summary class="muted small">Done in the last two weeks ({done.length})</summary>
      {#each done as a (a.id)}
        <label class="a-row done">
          <input type="checkbox" checked disabled={!canWrite} onchange={() => act(() => setActionDone(a.id, false))} aria-label={`Reopen: ${a.title}`} />
          <span class="a-name">{a.title}</span>
          {#if !filter}<span class="muted small"> · {where(a)}</span>{/if}
        </label>
      {/each}
    </details>
  {/if}
</section>

<style>
  .actions-box { border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.6rem 0.9rem; margin: 0.6rem 0 1rem; font-family: var(--font-ui); }
  header { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: baseline; }
  h2 { font-size: 1rem; margin: 0; }
  h2 .muted { font-weight: 400; font-size: 0.85rem; }
  .spacer { flex: 1; }
  .a-form { display: grid; gap: 0.4rem; margin: 0.5rem 0; }
  .a-form select { width: auto; max-width: 100%; font-size: 0.85rem; }
  .a-form textarea, .a-form input { font-size: 0.88rem; }
  .a-acts { display: flex; gap: 0.4rem; }
  .a-list { list-style: none; padding: 0; margin: 0.4rem 0 0; }
  .a-list li { padding: 0.3rem 0; border-top: 1px solid var(--rule); }
  .a-list li:first-child { border-top: none; }
  .a-row { display: inline-flex; gap: 0.45rem; align-items: baseline; cursor: pointer; }
  .a-row input { width: auto; }
  .a-row.done .a-name { text-decoration: line-through; color: var(--ink-soft); }
  .a-note { margin: 0.15rem 0 0 1.6rem; font-size: 0.85rem; color: var(--ink-soft); white-space: pre-wrap; }
  .a-links { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.25rem 0 0 1.6rem; font-size: 0.8rem; }
  .a-links a { padding: 0.05rem 0.45rem; border: 1px solid var(--rule); border-radius: 999px; text-decoration: none; }
  .a-done { margin-top: 0.4rem; }
  .a-done summary { cursor: pointer; }
  .a-done .a-row { display: flex; padding: 0.15rem 0; }
  .mini { font-size: 0.78rem; padding: 0.2rem 0.6rem; }
  .small { font-size: 0.8rem; }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.75rem; padding: 0 0.3rem; }
  .x:hover { color: var(--danger); }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0 0.3rem; font-size: 0.78rem; }
</style>
