<script lang="ts">
  import {
    saveGroupProject, deleteGroupProject, addProjectMember, removeProjectMember, saveMilestone, deleteMilestone,
  } from "./group";
  import type { GroupProject, GroupMilestone, Member, Entry } from "./group";
  import { fromMonth, fmtMonth } from "./pathways";
  import { today } from "./dates";

  type Props = {
    projects: GroupProject[];
    milestones: GroupMilestone[];
    members: Member[];
    entries: Entry[]; // to show how lively each project is
    supervisor: boolean; // creates projects, assigns people
    newFor?: string | null; // when set, "+ Project" puts this person on the new project
    onchanged: () => Promise<void>;
  };
  let { projects, milestones, members, entries, supervisor, newFor = null, onchanged }: Props = $props();

  let error = $state("");
  const act = async (f: () => Promise<unknown>) => {
    try { error = ""; await f(); await onchanged(); } catch (e) { error = (e as Error).message; }
  };
  const nameOf = (id: string) => members.find((m) => m.user_id === id)?.display_name ?? "—";
  const students = $derived(members.filter((m) => m.role !== "supervisor" && m.active));

  // ---- a project's details (new or edited) ------------------------------------------
  type Draft = { id: string | null; title: string; aim: string; status: GroupProject["status"]; start: string; end: string };
  let draft = $state<Draft | null>(null);
  function edit(p: GroupProject | null) {
    draft = p
      ? { id: p.id, title: p.title, aim: p.aim ?? "", status: p.status, start: (p.start_on ?? "").slice(0, 7), end: (p.end_on ?? "").slice(0, 7) }
      : { id: null, title: "", aim: "", status: "active", start: today().slice(0, 7), end: "" };
  }
  async function saveDraft(ev: SubmitEvent) {
    ev.preventDefault();
    const d = draft;
    if (!d || !d.title.trim()) return;
    const was = d.id ? projects.find((p) => p.id === d.id) : null;
    await act(async () => {
      const id = await saveGroupProject(d.id, {
        title: d.title.trim(), aim: d.aim.trim() || null, status: d.status,
        start_on: fromMonth(d.start, false, was?.start_on ?? null), end_on: fromMonth(d.end, true, was?.end_on ?? null),
      });
      if (!d.id && newFor) await addProjectMember(id, newFor);
      draft = null;
    });
  }

  // ---- milestones ----------------------------------------------------------------------
  let msText = $state<Record<string, string>>({});
  let msDue = $state<Record<string, string>>({});
  async function addMs(p: GroupProject) {
    const title = (msText[p.id] ?? "").trim();
    if (!title) return;
    const order = Math.max(0, ...milestones.filter((m) => m.project_id === p.id).map((m) => m.sort_order)) + 10;
    await act(() => saveMilestone(null, { project_id: p.id, title, due_on: fromMonth(msDue[p.id] ?? "", true), sort_order: order }));
    msText[p.id] = "";
    msDue[p.id] = "";
  }
  const tick = (m: GroupMilestone) => act(() => saveMilestone(m.id, { done: !m.done, done_on: m.done ? null : today() }));

  const recent = (p: GroupProject) => {
    const since = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
    return entries.filter((e) => e.project_id === p.id && e.entry_date >= since).length;
  };
  const lastEntry = (p: GroupProject) => entries.find((e) => e.project_id === p.id)?.entry_date ?? null;
</script>

{#if error}<p class="error">{error}</p>{/if}
{#if supervisor && !draft}<button class="add" onclick={() => edit(null)}>+ Project</button>{/if}

{#snippet editor()}
  {#if draft}
    <form class="gp-form" onsubmit={saveDraft}>
      <label class="wide">Title <input bind:value={draft.title} required /></label>
      <label class="wide">Aim <textarea rows="2" bind:value={draft.aim}></textarea></label>
      <label>Status
        <select bind:value={draft.status}><option value="active">active</option><option value="paused">paused</option><option value="done">done</option></select>
      </label>
      <label>From <input type="month" bind:value={draft.start} /></label>
      <label>To <input type="month" bind:value={draft.end} min={draft.start || undefined} /></label>
      <div class="wide actions">
        <button class="primary" type="submit">{draft.id ? "Save" : "Add project"}</button>
        <button type="button" onclick={() => (draft = null)}>Cancel</button>
      </div>
    </form>
  {/if}
{/snippet}
{#if draft && !draft.id}{@render editor()}{/if}

{#each projects as p (p.id)}
  {@const ms = milestones.filter((m) => m.project_id === p.id)}
  <section class="gp" class:quiet={p.status !== "active"}>
    {#if draft?.id === p.id}
      {@render editor()}
    {:else}
      <header>
        <h3>{p.title}</h3>
        <span class="muted small">
          {p.status}{p.start_on ? ` · ${fmtMonth(p.start_on)} → ${p.end_on ? fmtMonth(p.end_on) : "…"}` : ""}
          · {recent(p)} {recent(p) === 1 ? "entry" : "entries"} this week{lastEntry(p) ? ` · last ${lastEntry(p)}` : ""}
        </span>
        <span class="spacer"></span>
        <button class="mini" onclick={() => edit(p)}>Edit</button>
        {#if supervisor}
          <button class="mini danger" onclick={() => confirm(`Delete the project “${p.title}”? Its logbook entries stay, without a project.`) && act(() => deleteGroupProject(p.id))}>Delete</button>
        {/if}
      </header>
      {#if p.aim}<p class="aim">{p.aim}</p>{/if}
    {/if}

    <div class="people small">
      <span class="muted">People:</span>
      {#each p.members as uid (uid)}
        <span class="person">{nameOf(uid)}{#if supervisor}<button class="x" aria-label="Take off the project" onclick={() => act(() => removeProjectMember(p.id, uid))}>✕</button>{/if}</span>
      {:else}<span class="muted">nobody yet</span>{/each}
      {#if supervisor}
        {@const others = students.filter((s) => !p.members.includes(s.user_id))}
        {#if others.length}
          <select aria-label="Add someone" onchange={(ev) => { const v = (ev.target as HTMLSelectElement).value; if (v) act(() => addProjectMember(p.id, v)); }}>
            <option value="">+ add someone…</option>
            {#each others as s (s.user_id)}<option value={s.user_id}>{s.display_name}</option>{/each}
          </select>
        {/if}
      {/if}
    </div>

    <ul class="ms">
      {#each ms as m (m.id)}
        <li class:done={m.done}>
          <label><input type="checkbox" checked={m.done} onchange={() => tick(m)} /> {m.title}</label>
          {#if m.due_on}<span class="muted small">by {fmtMonth(m.due_on)}</span>{/if}
          {#if m.done && m.done_on}<span class="muted small">· done {m.done_on}</span>{/if}
          <button class="x" aria-label="Delete milestone" onclick={() => confirm(`Delete the milestone “${m.title}”?`) && act(() => deleteMilestone(m.id))}>✕</button>
        </li>
      {/each}
    </ul>
    <form class="ms-add" onsubmit={(ev) => { ev.preventDefault(); addMs(p); }}>
      <input bind:value={msText[p.id]} placeholder="New milestone…" aria-label="New milestone" />
      <input type="month" bind:value={msDue[p.id]} aria-label="Due by" title="Due by (optional)" />
      <button class="mini" type="submit" disabled={!(msText[p.id] ?? "").trim()}>Add</button>
    </form>
  </section>
{:else}
  <p class="muted">{supervisor ? "No projects yet." : "No projects yet — your supervisor adds them."}</p>
{/each}

<style>
  .add { margin-bottom: 0.7rem; }
  .gp { border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.7rem 0.9rem; margin-bottom: 0.8rem; font-family: var(--font-ui); }
  .gp.quiet { opacity: 0.7; }
  .gp header { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline; }
  .gp h3 { margin: 0; font-size: 1rem; }
  .spacer { flex: 1; }
  .aim { margin: 0.3rem 0; font-family: var(--font-body, inherit); white-space: pre-wrap; }
  .people { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.4rem 0; }
  .person { padding: 0.05rem 0.5rem; border: 1px solid var(--rule); border-radius: 999px; }
  .people select { width: auto; font-size: 0.78rem; padding: 0.1rem 0.3rem; }
  .ms { list-style: none; margin: 0.4rem 0; padding: 0; }
  .ms li { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: baseline; padding: 0.15rem 0; font-size: 0.88rem; }
  .ms li.done label { text-decoration: line-through; color: var(--ink-soft); }
  .ms label { display: inline-flex; gap: 0.35rem; align-items: baseline; }
  .ms input[type="checkbox"] { width: auto; }
  .ms-add { display: flex; gap: 0.4rem; }
  .ms-add input { font-size: 0.82rem; padding: 0.25rem 0.45rem; }
  .ms-add input[type="month"] { width: auto; }
  .gp-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.5rem 0.8rem; margin-bottom: 0.8rem; font-family: var(--font-ui); }
  .gp-form label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .gp-form .wide { grid-column: 1 / -1; }
  .actions { display: flex; gap: 0.5rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  .danger { color: var(--danger); }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.7rem; padding: 0 0.2rem; }
  .small { font-size: 0.8rem; }
  @media (max-width: 40rem) { .gp-form { grid-template-columns: 1fr; } }
</style>
