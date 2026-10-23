<script lang="ts">
  // The Logbook: a project's actions by milestone, each with its dated thread of
  // comments and links. Tick off what is done, add what comes up, drag to put
  // them in order. Members write on their own actions; the supervisor replies.
  import {
    addAction, saveAction, setActionDone, deleteAction, saveActionOrder, addActionComment, editActionComment, deleteActionComment,
    commentDeletable, byOrder,
  } from "./actions";
  import type { Action, ActionComment } from "./actions";
  import { parseLinks, linkName, planningGroups } from "./group";
  import type { GroupProject, GroupMilestone, Member, PlanningRef } from "./group";
  import { fmtDay } from "./dates";
  import Sortable from "./Sortable.svelte";

  type Props = {
    actions: Action[]; // open, and done in the last two weeks
    comments: ActionComment[];
    projects: GroupProject[];
    planning?: PlanningRef[];
    groupMilestones?: GroupMilestone[];
    filter: string; // "g:<id>", "p:<id>", or "" for every project
    members: Member[];
    me: string;
    canWrite: boolean; // the actions are yours
    canComment: boolean;
    onchanged: () => Promise<void>;
  };
  let { actions, comments, projects, planning = [], groupMilestones = [], filter, members, me, canWrite, canComment, onchanged }: Props = $props();

  let error = $state("");
  const act = async (f: () => Promise<unknown>) => {
    try { error = ""; await f(); await onchanged(); } catch (e) { error = (e as Error).message; }
  };
  const nameOf = (uid: string) => (uid === me ? "you" : members.find((m) => m.user_id === uid)?.display_name ?? "—");
  const keyOf = (a: Action) => (a.project_id ? `p:${a.project_id}` : a.group_project_id ? `g:${a.group_project_id}` : "");
  const msOf = (a: Action) => a.milestone_id ?? a.group_milestone_id ?? "";
  const projectName = (key: string) => key.startsWith("p:")
    ? planning.find((p) => p.id === key.slice(2))?.name ?? "Planning project"
    : projects.find((p) => p.id === key.slice(2))?.title ?? "Shared project";

  // ---- sections: project › milestone ---------------------------------------------------
  type Section = { project: string; ms: string; label: string; open: Action[]; done: Action[] };
  const sections = $derived.by(() => {
    const keys = filter ? [filter] : [...new Set(actions.map(keyOf).filter(Boolean))].sort((a, b) => projectName(a).localeCompare(projectName(b)));
    const out: Section[] = [];
    for (const key of keys) {
      const mine = actions.filter((a) => keyOf(a) === key);
      // a project's milestones: the active ones (so new actions can go under them), and any that have actions
      const ms: { id: string; title: string }[] = key.startsWith("p:")
        ? (planning.find((p) => p.id === key.slice(2))?.milestones ?? []).filter((m) => m.active !== false || mine.some((a) => msOf(a) === m.id))
        : groupMilestones.filter((m) => m.project_id === key.slice(2) && (!m.done || mine.some((a) => msOf(a) === m.id)));
      for (const m of [...ms, { id: "", title: "No milestone" }]) {
        const here = mine.filter((a) => msOf(a) === m.id || (m.id === "" && !ms.some((x) => x.id === msOf(a))));
        if (!here.length && (!filter || (m.id === "" && ms.length))) continue; // in the overview, only what has actions
        out.push({ project: key, ms: m.id, label: m.title, open: here.filter((a) => !a.is_done).sort(byOrder), done: here.filter((a) => a.is_done) });
      }
    }
    return out;
  });
  const threadOf = (a: Action) => comments.filter((c) => c.action_id === a.id);

  // ---- adding, renaming, ordering --------------------------------------------------------
  let adding = $state<Record<string, string>>({});
  async function add(s: Section) {
    const k = `${s.project}|${s.ms}`;
    const title = (adding[k] ?? "").trim();
    if (!title) return;
    adding[k] = "";
    const planningP = s.project.startsWith("p:");
    const last = Math.max(0, ...s.open.map((a) => a.sort_order));
    await act(() => addAction({
      title, links: [],
      project_id: planningP ? s.project.slice(2) : null, milestone_id: planningP ? s.ms || null : null,
      group_project_id: planningP ? null : s.project.slice(2), group_milestone_id: planningP ? null : s.ms || null,
    }, last + 10));
  }
  let renaming = $state<{ id: string; title: string } | null>(null);
  async function rename() {
    const r = renaming;
    renaming = null;
    if (r && r.title.trim()) await act(() => saveAction(r.id, { title: r.title.trim() }));
  }
  const reorder = (s: Section) => (ids: string[]) =>
    act(() => saveActionOrder(ids, new Map(s.open.map((a) => [a.id, a.sort_order]))));

  // ---- the new-action box in the overview (choose the project) ------------------------------
  let newTitle = $state("");
  let newProject = $state("");
  async function addAnywhere(ev: SubmitEvent) {
    ev.preventDefault();
    if (!newTitle.trim() || !newProject) return;
    const p = newProject.startsWith("p:");
    await act(() => addAction({
      title: newTitle.trim(), links: [], project_id: p ? newProject.slice(2) : null, milestone_id: null,
      group_project_id: p ? null : newProject.slice(2), group_milestone_id: null,
    }));
    newTitle = "";
  }

  // ---- comments ----------------------------------------------------------------------------------
  let open = $state<string | null>(null);
  let body = $state("");
  let links = $state("");
  async function comment(a: Action) {
    if (!body.trim() && !parseLinks(links).length) return;
    const b = body, l = parseLinks(links);
    body = links = "";
    open = null;
    await act(() => addActionComment(a.id, b, l));
  }
  let editing = $state<{ id: string; body: string; links: string } | null>(null);
  const escEdit = (ev: KeyboardEvent) => { if (ev.key === "Escape") editing = null; };
  async function saveEdit() {
    const e = editing;
    if (!e) return;
    const l = parseLinks(e.links);
    if (!e.body.trim() && !l.length) return; // emptying a comment is not deleting it
    editing = null;
    await act(() => editActionComment(e.id, e.body, l));
  }
</script>

{#if error}<p class="error">{error}</p>{/if}

{#if !filter && canWrite}
  <form class="anywhere" onsubmit={addAnywhere}>
    <input bind:value={newTitle} placeholder="New action…" aria-label="New action" />
    <select bind:value={newProject} aria-label="Project">
      <option value="">on project…</option>
      {#if projects.length}<optgroup label="Shared projects">{#each projects as p (p.id)}<option value={`g:${p.id}`}>{p.title}</option>{/each}</optgroup>{/if}
      {#each planningGroups(planning) as g (g.label)}
        <optgroup label={g.label}>{#each g.items as p (p.id)}<option value={`p:${p.id}`}>{p.name}</option>{/each}</optgroup>
      {/each}
    </select>
    <button class="mini primary" type="submit" disabled={!newTitle.trim() || !newProject}>Add</button>
    <span class="muted small">or pick a project above to work on it milestone by milestone</span>
  </form>
{/if}

{#snippet card(a: Action)}
  <div class="action" class:done={a.is_done}>
    <div class="a-head">
      <input type="checkbox" checked={a.is_done} disabled={!canWrite}
             onchange={() => act(() => setActionDone(a.id, !a.is_done))} aria-label={`${a.is_done ? "Reopen" : "Done"}: ${a.title}`} />
      {#if renaming?.id === a.id}
        <input class="rename" bind:value={renaming.title} onblur={rename}
               onkeydown={(ev) => { if (ev.key === "Enter") rename(); if (ev.key === "Escape") renaming = null; }} aria-label="Action" />
      {:else}
        <button class="a-title" disabled={!canWrite} title={canWrite ? "Click to rename" : ""}
                onclick={() => (renaming = { id: a.id, title: a.title })}>{a.title}</button>
      {/if}
      {#if a.group_project_id}
        <!-- on a shared project, who added it and who ticked it off, and when (only its author can do either) -->
        <span class="muted small logged">added {fmtDay(a.created_at.slice(0, 10))} by {nameOf(a.user_id)}{#if a.is_done && a.done_at}
          · done {fmtDay(a.done_at.slice(0, 10))} by {nameOf(a.user_id)}{/if}</span>
      {:else if a.done_at && a.is_done}<span class="muted small">done {fmtDay(a.done_at.slice(0, 10))}</span>{/if}
      {#each a.links as l (l)}<a class="chip" href={l} target="_blank" rel="noopener noreferrer" title={l}>↗ {linkName(l)}</a>{/each}
      <span class="spacer"></span>
      {#if canComment}<button class="link" onclick={() => { open = open === a.id ? null : a.id; body = links = ""; }}>comment / link</button>{/if}
      {#if canWrite}<button class="x" aria-label={`Delete ${a.title}`} title="Delete this action"
                            onclick={() => confirm(`Delete the action “${a.title}” and its comments?`) && act(() => deleteAction(a.id))}>✕</button>{/if}
    </div>
    {#if threadOf(a).length}
      <ul class="thread">
        {#each threadOf(a) as c (c.id)}
          <li>
            <span class="when">{fmtDay(c.created_at.slice(0, 10))}</span>
            {#if c.author_id !== me || members.length > 1}<span class="who">{nameOf(c.author_id)}</span>{/if}
            {#if editing?.id === c.id}
              <form class="cmt edit" onsubmit={(ev) => { ev.preventDefault(); saveEdit(); }}>
                <input bind:value={editing.body} placeholder="Comment" aria-label="Comment text" onkeydown={escEdit} />
                <input bind:value={editing.links} placeholder="Link(s)" aria-label="Comment links" onkeydown={escEdit} />
                <button class="mini" type="submit">Save</button>
                <button class="mini" type="button" onclick={() => (editing = null)}>Cancel</button>
              </form>
            {:else}
              {#if c.body}<span class="text">{c.body}</span>{/if}
              {#each c.links as l (l)}<a class="chip" href={l} target="_blank" rel="noopener noreferrer" title={l}>↗ {linkName(l)}</a>{/each}
              {#if c.edited_at}<span class="muted small" title={`Edited ${fmtDay(c.edited_at.slice(0, 10))}`}>(edited)</span>{/if}
              {#if c.author_id === me && canComment}
                <button class="x edit-btn" aria-label="Edit comment" title="Edit"
                        onclick={() => (editing = { id: c.id, body: c.body ?? "", links: c.links.join(" ") })}>✎</button>
              {/if}
              {#if c.author_id === me && commentDeletable(c)}
                <button class="x" aria-label="Delete comment" onclick={() => act(() => deleteActionComment(c.id))}>✕</button>
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
    {#if open === a.id}
      <form class="cmt" onsubmit={(ev) => { ev.preventDefault(); comment(a); }}>
        <input bind:value={body} placeholder="Comment" aria-label="Comment" />
        <input bind:value={links} placeholder="Link(s)" aria-label="Links" />
        <button class="mini" type="submit">Add</button>
      </form>
    {/if}
  </div>
{/snippet}

{#each sections as s, i (`${s.project}|${s.ms}`)}
  {#if !filter && (i === 0 || sections[i - 1].project !== s.project)}<h2 class="proj">{projectName(s.project)}</h2>{/if}
  <section class="ms">
    <h3>{s.label} <span class="muted">{s.open.length}</span></h3>
    <Sortable items={s.open} row={card} onreorder={reorder(s)} disabled={!canWrite} />
    {#each s.done as a (a.id)}{@render card(a)}{/each}
    {#if canWrite}
      <form class="add" onsubmit={(ev) => { ev.preventDefault(); add(s); }}>
        <input bind:value={adding[`${s.project}|${s.ms}`]} placeholder="+ action" aria-label={`New action under ${s.label}`} />
      </form>
    {/if}
  </section>
{:else}
  <p class="muted">{filter ? "No actions on this project yet." : canWrite ? "No open actions. Add one above, or pick a project." : "No actions yet."}</p>
{/each}

<style>
  .anywhere { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.4rem 0 1rem; font-family: var(--font-ui); }
  .anywhere input { flex: 1 1 14rem; font-size: 0.88rem; }
  .anywhere select { width: auto; font-size: 0.85rem; }
  .proj { font-size: 1.05rem; margin: 1.2rem 0 0.2rem; }
  .ms { margin: 0 0 0.9rem; font-family: var(--font-ui); }
  .ms h3 { font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-soft); margin: 0.6rem 0 0.25rem; }
  .ms h3 .muted { font-weight: 400; }
  .action { padding: 0.3rem 0; border-top: 1px solid var(--rule); }
  .a-head { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
  .a-head input[type="checkbox"] { width: auto; }
  .a-title { background: none; border: none; padding: 0; text-align: left; font-size: 0.92rem; color: var(--ink); cursor: text; }
  .a-title:disabled { cursor: default; }
  .done .a-title { text-decoration: line-through; color: var(--ink-soft); }
  .rename { flex: 1; font-size: 0.9rem; padding: 0.15rem 0.35rem; }
  .spacer { flex: 1; }
  .chip { font-size: 0.75rem; padding: 0 0.45rem; border: 1px solid var(--rule); border-radius: 999px; text-decoration: none; }
  .thread { list-style: none; margin: 0.2rem 0 0 1.5rem; padding: 0; font-size: 0.84rem; }
  .thread li { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: baseline; padding: 0.08rem 0; }
  .when { color: var(--ink-soft); font-size: 0.76rem; min-width: 4.8rem; }
  .who { font-weight: 600; font-size: 0.8rem; }
  .text { white-space: pre-wrap; }
  .cmt { display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.25rem 0 0 1.5rem; }
  .cmt input { flex: 1 1 12rem; font-size: 0.84rem; padding: 0.2rem 0.45rem; }
  .add input { width: 100%; font-size: 0.84rem; padding: 0.2rem 0.45rem; margin-top: 0.25rem; border-style: dashed; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  .small { font-size: 0.78rem; }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.72rem; padding: 0 0.25rem; }
  .x:hover { color: var(--danger); }
  .x.edit-btn:hover { color: var(--accent); }
  .cmt.edit { flex: 1 1 20rem; margin: 0; }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0 0.2rem; font-size: 0.75rem; }
</style>
