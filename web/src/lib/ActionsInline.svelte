<script lang="ts">
  // A project's actions inside Week's time log: tick off what the block
  // finished, add what came up, comment or link on any action, and drag them
  // into order. Each change is saved at once and noted for the block.
  import {
    loadMyActions, loadActionComments, addAction, setActionDone, addActionComment, noteStep, deleteAction, saveActionOrder, byOrder,
  } from "./actions";
  import type { Action, ActionComment, ActionStep } from "./actions";
  import { parseLinks, linkName } from "./group";
  import Sortable from "./Sortable.svelte";

  type Props = {
    projectKey: string; // "p:<id>" a Planning project, "g:<id>" a shared one
    milestoneId?: string; // a Planning milestone, to narrow to (and to file new actions under)
    log: ActionStep[]; // what this block has done so far
    onlog: (log: ActionStep[]) => void;
  };
  let { projectKey, milestoneId = "", log, onlog }: Props = $props();

  let all = $state<Action[]>([]);
  let thread = $state<ActionComment[]>([]);
  let error = $state("");
  const isPlanning = $derived(projectKey.startsWith("p:"));
  const pid = $derived(projectKey.slice(2));
  const inProject = (a: Action) => (isPlanning ? a.project_id === pid : a.group_project_id === pid);
  async function refresh() {
    all = await loadMyActions();
    thread = await loadActionComments(all.filter(inProject).map((a) => a.id));
  }
  refresh();

  // the milestone's own actions first, then the project's others, each in your order
  const shown = $derived.by(() => {
    const open = all.filter((a) => !a.is_done && inProject(a)).sort(byOrder);
    return milestoneId ? [...open.filter((a) => a.milestone_id === milestoneId), ...open.filter((a) => a.milestone_id !== milestoneId)] : open;
  });
  const doneHere = $derived(all.filter((a) => a.is_done && log.some((s) => s.id === a.id && s.what.includes("done"))));
  const lastComment = (a: Action) => thread.filter((c) => c.action_id === a.id).at(-1);

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
        title: t, links: [],
        project_id: isPlanning ? pid : null, milestone_id: isPlanning ? milestoneId || null : null,
        group_project_id: isPlanning ? null : pid, group_milestone_id: null,
      }, Math.max(0, ...shown.map((a) => a.sort_order)) + 10);
      onlog(noteStep(log, { id, title: t }, "added"));
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }
  async function remove(a: Action) {
    if (!confirm(`Delete the action “${a.title}” and its comments?`)) return;
    try {
      error = "";
      await deleteAction(a.id);
      onlog(log.filter((s) => s.id !== a.id)); // no longer part of this block
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }
  async function reorder(ids: string[]) {
    try { await saveActionOrder(ids, new Map(shown.map((a) => [a.id, a.sort_order]))); await refresh(); }
    catch (e) { error = (e as Error).message; }
  }

  let open = $state<string | null>(null); // the action being commented on
  let comment = $state("");
  let links = $state("");
  async function saveComment(a: Action) {
    if (!comment.trim() && !parseLinks(links).length) return void (open = null);
    const c = comment, l = parseLinks(links);
    open = null;
    await step(() => addActionComment(a.id, c, l), a, "updated");
  }
</script>

{#snippet row(a: Action)}
  {@const last = lastComment(a)}
  <div class="item">
    <label class="row">
      <input type="checkbox" onchange={() => step(() => setActionDone(a.id, true), a, "done")} aria-label={`Done: ${a.title}`} />
      <span>{a.title}</span>
    </label>
    <button type="button" class="link" onclick={() => { open = open === a.id ? null : a.id; comment = links = ""; }}>comment / link</button>
    <button type="button" class="x" title="Delete this action" aria-label={`Delete ${a.title}`} onclick={() => remove(a)}>✕</button>
    {#if last}<p class="note">{last.created_at.slice(0, 10)}: {last.body ?? ""}{#each last.links as l (l)} <a href={l} target="_blank" rel="noopener noreferrer">↗ {linkName(l)}</a>{/each}</p>{/if}
    {#if open === a.id}
      <div class="cmt">
        <input bind:value={comment} placeholder="Comment" aria-label="Comment" />
        <input bind:value={links} placeholder="Link(s)" aria-label="Links" />
        <button type="button" class="mini" onclick={() => saveComment(a)}>Add</button>
      </div>
    {/if}
  </div>
{/snippet}

<div class="ai">
  <span class="ai-head">Actions{shown.length ? ` · ${shown.length} open` : ""}</span>
  {#if error}<p class="error">{error}</p>{/if}
  <Sortable items={shown} {row} onreorder={reorder} />
  {#each doneHere as a (a.id)}
    <label class="row done">
      <input type="checkbox" checked onchange={() => step(() => setActionDone(a.id, false), a, "updated")} aria-label={`Reopen: ${a.title}`} />
      <span>{a.title}</span>
    </label>
  {/each}
  <div class="new">
    <input bind:value={title} placeholder="New action from this block…" aria-label="New action"
           onkeydown={(ev) => { if (ev.key === "Enter") add(ev); }} />
    <button type="button" class="mini" disabled={!title.trim()} onclick={add}>Add</button>
  </div>
</div>

<style>
  .ai { border: 1px dashed var(--rule); border-radius: var(--radius); padding: 0.45rem 0.65rem; font-family: var(--font-ui); font-size: 0.85rem; display: grid; gap: 0.3rem; }
  .ai-head { font-size: 0.78rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.05em; }
  .item { padding: 0.1rem 0; }
  .row { display: inline-flex; gap: 0.4rem; align-items: baseline; cursor: pointer; }
  .row input { width: auto; }
  .row.done span { text-decoration: line-through; color: var(--ink-soft); }
  .note { margin: 0.1rem 0 0 1.5rem; font-size: 0.78rem; color: var(--ink-soft); }
  .cmt { display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.2rem 0 0 1.5rem; }
  .cmt input { flex: 1 1 12rem; font-size: 0.82rem; padding: 0.2rem 0.4rem; }
  .new { display: flex; gap: 0.35rem; }
  .new input { flex: 1; font-size: 0.85rem; padding: 0.25rem 0.45rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.75rem; padding: 0 0.3rem; }
  .x:hover { color: var(--danger); }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0 0.3rem; font-size: 0.75rem; }
</style>
