<script lang="ts">
  // A project's (or milestone's) action items inside a session: tick off what
  // was finished, add what came up, and comment or link on any action. Each
  // change is saved at once and reported to the session.
  import { loadMyActions, addAction, setActionDone, addToAction, noteStep, deleteAction } from "./actions";
  import type { Action, ActionStep } from "./actions";
  import { parseLinks, linkName } from "./group";

  type Props = {
    projectKey: string; // "p:<id>" a Planning project, "g:<id>" a shared one
    milestoneId?: string; // a Planning milestone, to narrow to (and to file new actions under)
    log: ActionStep[]; // what this session has done so far
    onlog: (log: ActionStep[]) => void;
  };
  let { projectKey, milestoneId = "", log, onlog }: Props = $props();

  let all = $state<Action[]>([]);
  let error = $state("");
  const refresh = async () => { all = await loadMyActions(); };
  refresh();

  const isPlanning = $derived(projectKey.startsWith("p:"));
  const pid = $derived(projectKey.slice(2));
  // the milestone's own actions first, then the project's others
  const shown = $derived(
    all.filter((a) => !a.is_done && (isPlanning ? a.project_id === pid : a.group_project_id === pid))
      .sort((a, b) => Number(b.milestone_id === milestoneId && !!milestoneId) - Number(a.milestone_id === milestoneId && !!milestoneId)),
  );
  const doneHere = $derived(all.filter((a) => a.is_done && log.some((s) => s.id === a.id && s.what.includes("done"))));

  async function step(f: () => Promise<unknown>, a: { id: string; title: string }, what: ActionStep["what"][number]) {
    try {
      error = "";
      await f();
      onlog(noteStep(log, a, what));
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  let title = $state("");
  async function add(ev: Event) {
    ev.preventDefault();
    const t = title.trim();
    if (!t) return;
    title = "";
    try {
      error = "";
      const id = await addAction({
        title: t, note: null, links: [],
        project_id: isPlanning ? pid : null, milestone_id: isPlanning ? milestoneId || null : null,
        group_project_id: isPlanning ? null : pid,
      });
      onlog(noteStep(log, { id, title: t }, "added"));
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function remove(a: Action) {
    if (!confirm(`Delete the action “${a.title}”?`)) return;
    try {
      error = "";
      await deleteAction(a.id);
      onlog(log.filter((s) => s.id !== a.id)); // no longer part of this session
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  let open = $state<string | null>(null); // the action being commented on
  let comment = $state("");
  let links = $state("");
  function startComment(a: Action) {
    open = a.id;
    comment = links = "";
  }
  async function saveComment(a: Action) {
    if (!comment.trim() && !parseLinks(links).length) return void (open = null);
    await step(() => addToAction(a, comment, parseLinks(links)), a, "updated");
    open = null;
  }
</script>

<div class="ai">
  <span class="ai-head">Action items{shown.length ? ` · ${shown.length} open` : ""}</span>
  {#if error}<p class="error">{error}</p>{/if}
  <ul>
    {#each shown as a (a.id)}
      <li>
        <label class="row">
          <input type="checkbox" onchange={() => step(() => setActionDone(a.id, true), a, "done")} aria-label={`Done: ${a.title}`} />
          <span>{a.title}</span>
        </label>
        {#if a.links.length}
          <span class="links">{#each a.links as l (l)}<a href={l} target="_blank" rel="noopener noreferrer" title={l}>↗ {linkName(l)}</a>{/each}</span>
        {/if}
        <button type="button" class="link" onclick={() => (open === a.id ? (open = null) : startComment(a))}>comment / link</button>
        <button type="button" class="x" title="Delete this action" aria-label={`Delete ${a.title}`} onclick={() => remove(a)}>✕</button>
        {#if a.note}<p class="note">{a.note}</p>{/if}
        {#if open === a.id}
          <div class="cmt">
            <input bind:value={comment} placeholder="Comment (dated, added to its notes)" aria-label="Comment" />
            <input bind:value={links} placeholder="Link(s)" aria-label="Links" />
            <button type="button" class="mini" onclick={() => saveComment(a)}>Add</button>
          </div>
        {/if}
      </li>
    {/each}
    {#each doneHere as a (a.id)}
      <li class="done">
        <label class="row">
          <input type="checkbox" checked onchange={() => step(() => setActionDone(a.id, false), a, "updated")} aria-label={`Reopen: ${a.title}`} />
          <span>{a.title}</span>
        </label>
      </li>
    {/each}
  </ul>
  <div class="new">
    <input bind:value={title} placeholder="New action from this session…" aria-label="New action"
           onkeydown={(ev) => { if (ev.key === "Enter") add(ev); }} />
    <button type="button" class="mini" disabled={!title.trim()} onclick={add}>Add</button>
  </div>
</div>

<style>
  .ai { border: 1px dashed var(--rule); border-radius: var(--radius); padding: 0.45rem 0.65rem; font-family: var(--font-ui); font-size: 0.85rem; display: grid; gap: 0.3rem; }
  .ai-head { font-size: 0.78rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.05em; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { padding: 0.15rem 0; }
  .row { display: inline-flex; gap: 0.4rem; align-items: baseline; cursor: pointer; }
  .row input { width: auto; }
  li.done span { text-decoration: line-through; color: var(--ink-soft); }
  .links { display: inline-flex; flex-wrap: wrap; gap: 0.3rem; margin-left: 0.4rem; font-size: 0.78rem; }
  .links a { padding: 0 0.4rem; border: 1px solid var(--rule); border-radius: 999px; text-decoration: none; }
  .note { margin: 0.1rem 0 0 1.5rem; font-size: 0.8rem; color: var(--ink-soft); white-space: pre-wrap; }
  .cmt { display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.2rem 0 0 1.5rem; }
  .cmt input { flex: 1 1 12rem; font-size: 0.82rem; padding: 0.2rem 0.4rem; }
  .new { display: flex; gap: 0.35rem; }
  .new input { flex: 1; font-size: 0.85rem; padding: 0.25rem 0.45rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.75rem; padding: 0 0.3rem; }
  .x:hover { color: var(--danger); }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0 0.3rem; font-size: 0.75rem; }
</style>
