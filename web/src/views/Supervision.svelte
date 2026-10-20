<script lang="ts">
  import {
    loadMembers, addMember, saveMember, loadGroupProjects, loadMilestones, loadEntries, loadComments, revisionCounts,
    logbookMarkdown, download, myId,
  } from "../lib/group";
  import type { Member, GroupProject, GroupMilestone, Entry, Comment } from "../lib/group";
  import Logbook from "../lib/Logbook.svelte";
  import GroupProjects from "../lib/GroupProjects.svelte";

  let me = $state("");
  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let milestones = $state<GroupMilestone[]>([]);
  let entries = $state<Entry[]>([]);
  let comments = $state<Comment[]>([]);
  let edits = $state(new Map<string, number>());
  let loading = $state(true);
  let error = $state("");

  async function load() {
    try {
      const [id, m, p, ms, es] = await Promise.all([myId(), loadMembers(), loadGroupProjects(), loadMilestones(), loadEntries()]);
      const ids = es.map((e) => e.id);
      const [cs, ed] = await Promise.all([loadComments(ids), revisionCounts(ids)]);
      [me, members, projects, milestones, entries, comments, edits] = [id, m, p, ms, es, cs, ed];
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  // ---- Supervision › a student -------------------------------------------------------
  const SEL_KEY = "supervision.student";
  let selected = $state<string | null>((() => { try { return localStorage.getItem(SEL_KEY); } catch { return null; } })());
  function pick(id: string) {
    selected = id;
    adding = false;
    try { localStorage.setItem(SEL_KEY, id); } catch {}
  }
  const people = $derived(members.filter((m) => m.role !== "supervisor"));
  const current = $derived(people.find((m) => m.user_id === selected) ?? people.find((m) => m.active) ?? null);
  let tab = $state<"projects" | "logbook">("logbook");

  const theirProjects = $derived(current ? projects.filter((p) => p.members.includes(current.user_id)) : []);
  const theirEntries = $derived(current ? entries.filter((e) => e.author_id === current.user_id) : []);
  const since = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
  const lastOf = (uid: string) => entries.find((e) => e.author_id === uid)?.entry_date ?? null;
  const weekOf = (uid: string) => entries.filter((e) => e.author_id === uid && e.entry_date >= since).length;
  /** Entries with no comment from you yet. */
  const unanswered = (uid: string) =>
    entries.filter((e) => e.author_id === uid && !comments.some((c) => c.entry_id === e.id && c.author_id === me)).length;

  // ---- adding a student ----------------------------------------------------------------
  let adding = $state(false);
  let newEmail = $state("");
  let newName = $state("");
  let newRole = $state<"student" | "collaborator">("student");
  async function add(ev: SubmitEvent) {
    ev.preventDefault();
    try {
      await addMember(newEmail, newName, newRole);
      newEmail = newName = "";
      adding = false;
      await load();
    } catch (e) {
      error = (e as Error).message;
    }
  }
  async function rename(m: Member) {
    const name = prompt("Name", m.display_name)?.trim();
    if (!name || name === m.display_name) return;
    try { await saveMember(m.user_id, { display_name: name }); await load(); } catch (e) { error = (e as Error).message; }
  }
  async function setActive(m: Member, active: boolean) {
    if (!active && !confirm(`Take ${m.display_name} out of the group? They will no longer see anything here; their logbook stays, and you can bring them back.`)) return;
    try { await saveMember(m.user_id, { active }); await load(); } catch (e) { error = (e as Error).message; }
  }
  const myself = $derived(members.find((m) => m.user_id === me));

  // ---- export --------------------------------------------------------------------------
  function exportOne(m: Member) {
    download(`logbook-${m.display_name.replace(/\W+/g, "-").toLowerCase()}.md`,
      logbookMarkdown(theirEntries, projects, members, comments, edits, `Logbook — ${m.display_name}`));
  }
  function exportAll() {
    download(`logbooks-${new Date().toISOString().slice(0, 10)}.md`,
      logbookMarkdown(entries, projects, members, comments, edits, "Group logbooks"));
  }
</script>

<section class="sup">
  <span class="eyebrow">Supervision</span>
  <h1>Supervision</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{/if}

  <div class="layout">
    <nav class="people" aria-label="Students">
      <h2>Supervision</h2>
      {#each people as m (m.user_id)}
        <button class="who" class:on={current?.user_id === m.user_id} class:inactive={!m.active} onclick={() => pick(m.user_id)}>
          <span class="name">{m.display_name}</span>
          <span class="meta">
            {m.role === "collaborator" ? "collaborator · " : ""}{m.active ? `${weekOf(m.user_id)} this week` : "not in the group"}
            {#if unanswered(m.user_id)} · <strong>{unanswered(m.user_id)} to read</strong>{/if}
          </span>
        </button>
      {:else}
        {#if !loading}<p class="muted small">Nobody yet.</p>{/if}
      {/each}
      <button class="add" onclick={() => (adding = !adding)}>+ Add a student</button>
      {#if entries.length}<button class="add" onclick={exportAll}>Export all logbooks</button>{/if}
      {#if myself}
        <p class="muted small">You appear to them as <button class="link" onclick={() => rename(myself)}>{myself.display_name}</button></p>
      {/if}
    </nav>

    <div class="main">
      {#if adding}
        <form class="add-form" onsubmit={add}>
          <h2>Add a student</h2>
          <ol class="small">
            <li>In Supabase: <em>Authentication › Users › Invite user</em>, with their email. They get a link to set a password.</li>
            <li>Then add them here, with the same email.</li>
          </ol>
          <label>Email <input type="email" bind:value={newEmail} required /></label>
          <label>Name <input bind:value={newName} required /></label>
          <label>As
            <select bind:value={newRole}><option value="student">student</option><option value="collaborator">collaborator</option></select>
          </label>
          <div class="actions">
            <button class="primary" type="submit">Add</button>
            <button type="button" onclick={() => (adding = false)}>Cancel</button>
          </div>
        </form>
      {:else if current}
        <header class="head">
          <h2>{current.display_name}</h2>
          <span class="muted small">{current.email ?? ""}{lastOf(current.user_id) ? ` · last entry ${lastOf(current.user_id)}` : ""}</span>
          <span class="spacer"></span>
          <button class="mini" onclick={() => rename(current)}>Rename</button>
          <button class="mini" onclick={() => exportOne(current)} disabled={!theirEntries.length}>Export logbook</button>
          {#if current.active}<button class="mini" onclick={() => setActive(current, false)}>Take out of the group</button>
          {:else}<button class="mini" onclick={() => setActive(current, true)}>Bring back</button>{/if}
        </header>
        <div class="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "logbook"} class:on={tab === "logbook"} onclick={() => (tab = "logbook")}>Logbook ({theirEntries.length})</button>
          <button role="tab" aria-selected={tab === "projects"} class:on={tab === "projects"} onclick={() => (tab = "projects")}>Projects ({theirProjects.length})</button>
        </div>
        {#if tab === "projects"}
          <GroupProjects projects={theirProjects} {milestones} {members} {entries} supervisor newFor={current.user_id} onchanged={load} />
        {:else}
          <Logbook entries={theirEntries} projects={theirProjects} {members} {comments} {edits} {me} canWrite={false} onchanged={load} />
        {/if}
      {:else if !loading}
        <p class="muted">Add your first student to start: they write their logbook here, and you comment.</p>
      {/if}
    </div>
  </div>
</section>

<style>
  .layout { display: grid; grid-template-columns: 15rem minmax(0, 1fr); gap: 1.2rem; align-items: start; margin-top: 0.8rem; }
  .people { display: grid; gap: 0.3rem; font-family: var(--font-ui); position: sticky; top: 4rem; }
  .people h2 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-soft); margin: 0 0 0.2rem; }
  .who { display: grid; gap: 0.1rem; text-align: left; padding: 0.45rem 0.6rem; background: none; border: 1px solid transparent; }
  .who:hover { border-color: var(--rule); }
  .who.on { background: var(--panel); border-color: var(--rule); }
  .who.inactive { opacity: 0.55; }
  .who .name { font-weight: 600; }
  .who .meta { font-size: 0.75rem; color: var(--ink-soft); }
  .add { font-size: 0.82rem; margin-top: 0.3rem; }
  .head { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline; font-family: var(--font-ui); }
  .head h2 { margin: 0; }
  .spacer { flex: 1; }
  .tabs { display: flex; gap: 0.25rem; margin: 0.6rem 0 0.8rem; font-family: var(--font-ui); }
  .tabs button { font-size: 0.85rem; padding: 0.3rem 0.8rem; }
  .tabs button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .add-form { display: grid; gap: 0.6rem; max-width: 28rem; font-family: var(--font-ui); }
  .add-form label { display: grid; gap: 0.25rem; font-size: 0.85rem; }
  .add-form h2 { margin: 0; }
  .actions { display: flex; gap: 0.5rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  .small { font-size: 0.8rem; }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0; font-size: inherit; }
  @media (max-width: 44rem) { .layout { grid-template-columns: 1fr; } .people { position: static; } }
</style>
