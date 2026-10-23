<script lang="ts">
  // Members: you first (the projects you lead, your logbook), then each member
  // with their projects and logbook. A member is picked from your Planning
  // projects under Research › Supervision, which already name them.
  import {
    loadMembers, addMember, saveMember, loadGroupProjects, loadMilestones, loadEntries, loadComments, revisionCounts,
    logbookMarkdown, download, myId,
  } from "../lib/group";
  import type { Member, GroupProject, GroupMilestone, Entry, Comment, PlanningRef } from "../lib/group";
  import { loadProjects, loadTaxonomy } from "../lib/data";
  import type { Project } from "../lib/data";
  import { LIVE_STATUSES } from "../lib/plan";
  import { quietly } from "../lib/undo.svelte";
  import Logbook from "../lib/Logbook.svelte";
  import ActionLog from "../lib/ActionLog.svelte";
  import {
    loadMemberActions, loadMyActions, loadDoneActions, loadActionComments, loadRecentComments, loadProjectActivity, actionsMarkdown,
  } from "../lib/actions";
  import type { Action, ActionComment } from "../lib/actions";
  import GroupProjects from "../lib/GroupProjects.svelte";
  import { preview } from "../lib/preview.svelte";

  let me = $state("");
  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let milestones = $state<GroupMilestone[]>([]);
  let entries = $state<Entry[]>([]);
  let comments = $state<Comment[]>([]);
  let edits = $state(new Map<string, number>());
  let theirActions = $state<Action[]>([]); // the selected person's actions
  let theirThread = $state<ActionComment[]>([]); // and their comments (with your replies)
  let recent = $state<ActionComment[]>([]); // the last month's comments you can see, for the counts
  let activity = $state(new Map<string, number>()); // comments on each shared project's actions this week
  let supervision = $state<Project[]>([]); // your Planning projects under Research › Supervision
  let planningRefs = $state<PlanningRef[]>([]); // all your Planning projects, to name your own logbook notes
  let loading = $state(true);
  let error = $state("");

  async function load() {
    try {
      const [id, m, p, ms, es, planning, tax] = await Promise.all([
        myId(), loadMembers(), loadGroupProjects(), loadMilestones(), loadEntries(), loadProjects(), loadTaxonomy(),
      ]);
      const ids = es.map((e) => e.id);
      const [cs, ed] = await Promise.all([loadComments(ids), revisionCounts(ids)]);
      const supCats = new Set(tax.allCategories.filter((c) => c.code === "RES_SUP").map((c) => c.id));
      supervision = planning.filter((x) => supCats.has(x.category_id));
      planningRefs = planning.map((x) => ({ id: x.id, name: x.name, milestones: x.milestone.map((m) => ({ id: m.id, title: m.title, active: m.status === "active" })) }));
      // names follow Planning: rename a member there and it shows here (and to them)
      const renames = m.filter((x) => {
        const pp = x.planning_project_id ? planning.find((y) => y.id === x.planning_project_id) : null;
        return pp && pp.name !== x.display_name;
      });
      if (renames.length) {
        await quietly(async () => {
          for (const x of renames) await saveMember(x.user_id, { display_name: planning.find((y) => y.id === x.planning_project_id)!.name });
        });
        for (const x of renames) x.display_name = planning.find((y) => y.id === x.planning_project_id)!.name;
      }
      [me, members, projects, milestones, entries, comments, edits] = [id, m, p, ms, es, cs, ed];
      [recent, activity] = await Promise.all([loadRecentComments(30), loadProjectActivity(since)]);
      await loadThread();
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  // ---- Members › a person (you first) ---------------------------------------------------
  const SEL_KEY = "supervision.student";
  let selected = $state<string | null>((() => { try { return localStorage.getItem(SEL_KEY); } catch { return null; } })());
  function pick(id: string) {
    selected = id;
    adding = false;
    try { localStorage.setItem(SEL_KEY, id); } catch {}
  }
  const myself = $derived(members.find((m) => m.user_id === me) ?? null);
  const others = $derived(members.filter((m) => m.user_id !== me));
  const people = $derived(myself ? [myself, ...others] : others);
  const current = $derived(people.find((m) => m.user_id === selected) ?? myself ?? people[0] ?? null);
  const isMe = $derived(!!current && current.user_id === me);
  let tab = $state<"projects" | "logbook">("projects");

  const theirProjects = $derived(current ? projects.filter((p) => p.members.includes(current.user_id) || p.lead_id === current.user_id) : []);
  async function loadThread() {
    const c = current;
    if (!c) return;
    const acts = c.user_id === me ? await loadMyActions() : await loadMemberActions(c.user_id);
    const th = await loadActionComments(acts.map((a) => a.id));
    if (current?.user_id === c.user_id) [theirActions, theirThread] = [acts, th];
  }
  $effect(() => {
    if (current?.user_id) loadThread();
  });
  const theirEntries = $derived(current ? entries.filter((e) => e.author_id === current.user_id) : []);
  const since = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
  // how active each person is, from their comments on actions
  const lastOf = (uid: string) => recent.find((c) => c.author_id === uid)?.created_at.slice(0, 10) ?? null;
  const weekOf = (uid: string) => recent.filter((c) => c.author_id === uid && c.created_at.slice(0, 10) >= since).length;
  /** A member's actions where they wrote last: waiting for you to read (or reply). */
  const unanswered = (uid: string) => {
    const latest = new Map<string, ActionComment>();
    for (const c of recent) if (!latest.has(c.action_id)) latest.set(c.action_id, c); // newest first
    return [...latest.values()].filter((c) => c.author_id === uid && uid !== me).length;
  };
  const fromPlanning = (m: Member) => !!m.planning_project_id && supervision.some((p) => p.id === m.planning_project_id);

  // ---- adding a member -------------------------------------------------------------------
  let adding = $state(false);
  let newEmail = $state("");
  let newFrom = $state(""); // a Planning Supervision project id, or "other"
  let newName = $state("");
  const linked = $derived(new Set(members.map((m) => m.planning_project_id).filter(Boolean)));
  const choices = $derived(
    supervision.filter((p) => !linked.has(p.id) && LIVE_STATUSES.has(p.status)).sort((a, b) => a.name.localeCompare(b.name)),
  );
  function openAdd() {
    adding = true;
    newEmail = newName = "";
    newFrom = choices[0]?.id ?? "other";
  }
  async function add(ev: SubmitEvent) {
    ev.preventDefault();
    const pp = supervision.find((p) => p.id === newFrom);
    const name = pp ? pp.name : newName.trim();
    if (!name) return (error = "Give them a name.");
    try {
      await addMember(newEmail, name, pp?.id ?? null);
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

  // ---- export --------------------------------------------------------------------------------
  const whereOf = (a: Action) => {
    const m = milestones.find((x) => x.id === a.group_milestone_id);
    if (a.project_id) {
      const p = planningRefs.find((x) => x.id === a.project_id);
      const pm = p?.milestones.find((x) => x.id === a.milestone_id);
      return `${p?.name ?? "Planning project"}${pm ? ` › ${pm.title}` : ""}`;
    }
    return `${projects.find((x) => x.id === a.group_project_id)?.title ?? "Shared project"}${m ? ` › ${m.title}` : ""}`;
  };
  const nameOf = (uid: string) => members.find((x) => x.user_id === uid)?.display_name ?? "—";
  /** One person's logbook: their actions (all, done included) with threads, then any earlier entries. */
  async function logbookOf(m: Member): Promise<string> {
    const acts = m.user_id === me ? [...(await loadMyActions()).filter((a) => !a.is_done), ...(await loadDoneActions())] : await loadMemberActions(m.user_id);
    const th = await loadActionComments(acts.map((a) => a.id));
    let text = actionsMarkdown(acts, th, `Logbook — ${m.display_name}`, whereOf, nameOf);
    const old = entries.filter((e) => e.author_id === m.user_id);
    if (old.length) text += "\n\n" + logbookMarkdown(old, projects, members, comments, edits, "Earlier entries", planningRefs, milestones);
    return text;
  }
  async function exportOne(m: Member) {
    download(`logbook-${m.display_name.replace(/\W+/g, "-").toLowerCase()}.md`, await logbookOf(m));
  }
  async function exportAll() {
    const parts = [];
    for (const m of people) parts.push(await logbookOf(m));
    download(`logbooks-${new Date().toISOString().slice(0, 10)}.md`, parts.join("\n\n---\n\n"));
  }
</script>

<section class="sup">
  <span class="eyebrow">Members</span>
  <h1>Members</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{/if}

  <div class="layout">
    <nav class="people" aria-label="Members">
      {#each people as m (m.user_id)}
        <button class="who" class:on={current?.user_id === m.user_id} class:inactive={!m.active} onclick={() => pick(m.user_id)}>
          <span class="name">{m.user_id === me ? `You (${m.display_name})` : m.display_name}</span>
          <span class="meta">
            {#if m.user_id === me}
              {projects.filter((p) => p.lead_id === me).length} led · {weekOf(m.user_id)} comments this week
            {:else}
              {m.active ? `${weekOf(m.user_id)} this week` : "not in the group"}
              {#if unanswered(m.user_id)} · <strong>{unanswered(m.user_id)} to read</strong>{/if}
            {/if}
          </span>
        </button>
      {/each}
      <button class="add" onclick={openAdd}>+ Add a member</button>
      <button class="add" onclick={exportAll}>Export all logbooks</button>
    </nav>

    <div class="main">
      {#if adding}
        <form class="add-form" onsubmit={add}>
          <h2>Add a member</h2>
          <ol class="small">
            <li>In Supabase: <em>Authentication › Users › Invite user</em>, with their email. They get a link to choose a password.</li>
            <li>Then add them here, with the same email.</li>
          </ol>
          <label>Who
            <select bind:value={newFrom}>
              {#each choices as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
              <option value="other">Someone not under Supervision in Planning…</option>
            </select>
          </label>
          {#if !choices.length}<p class="muted small">Everyone under Research › Supervision in Planning is already a member.</p>{/if}
          {#if newFrom === "other"}<label>Name <input bind:value={newName} required /></label>{/if}
          <label>Email <input type="email" bind:value={newEmail} required /></label>
          <div class="actions">
            <button class="primary" type="submit">Add</button>
            <button type="button" onclick={() => (adding = false)}>Cancel</button>
          </div>
        </form>
      {:else if current}
        <header class="head">
          <h2>{isMe ? "You" : current.display_name}</h2>
          <span class="muted small">
            {isMe ? `shown to members as ${current.display_name}` : current.email ?? ""}{lastOf(current.user_id) ? ` · last comment ${lastOf(current.user_id)}` : ""}
          </span>
          <span class="spacer"></span>
          {#if fromPlanning(current)}
            <span class="muted small" title="Their name comes from their project under Research › Supervision in Planning; rename it there.">name from Planning</span>
          {:else}
            <button class="mini" onclick={() => rename(current)}>Rename</button>
          {/if}
          {#if !isMe && current.active}
            <button class="mini" onclick={() => { preview.as = current; location.hash = "#/logbook"; }}
                    title="Their Logbook and Projects, exactly as they see them (read-only); their Reading list stays private">See what they see</button>
          {/if}
          <button class="mini" onclick={() => exportOne(current)}>Export logbook</button>
          {#if !isMe}
            {#if current.active}<button class="mini" onclick={() => setActive(current, false)}>Take out of the group</button>
            {:else}<button class="mini" onclick={() => setActive(current, true)}>Bring back</button>{/if}
          {/if}
        </header>
        <div class="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "projects"} class:on={tab === "projects"} onclick={() => (tab = "projects")}>Projects ({theirProjects.length})</button>
          <button role="tab" aria-selected={tab === "logbook"} class:on={tab === "logbook"} onclick={() => (tab = "logbook")}>Logbook ({theirActions.filter((a) => !a.is_done).length} open)</button>
        </div>
        {#if tab === "projects"}
          <GroupProjects projects={theirProjects} {milestones} {members} {activity} supervisor newFor={current.user_id} onchanged={load} />
        {:else}
          {#if isMe}<p class="muted small">Write in your <a href="#/logbook">Logbook</a> tab; it's shown here too.</p>{/if}
          <ActionLog actions={theirActions} comments={theirThread} projects={isMe ? projects : theirProjects} planning={isMe ? planningRefs : []}
                     groupMilestones={milestones} filter="" {members} {me} canWrite={isMe} canComment onchanged={loadThread} />
          {#if theirEntries.length}
            <details class="old">
              <summary>Earlier entries ({theirEntries.length})</summary>
              <Logbook entries={theirEntries} projects={theirProjects} planning={isMe ? planningRefs : []} groupMilestones={milestones} {members} {comments} {edits} {me} canWrite={false} onchanged={load} />
            </details>
          {/if}
        {/if}
      {:else if !loading}
        <p class="muted">Add your first member: they write their logbook here, and you comment.</p>
      {/if}
    </div>
  </div>
</section>

<style>
  .layout { display: grid; grid-template-columns: 15rem minmax(0, 1fr); gap: 1.2rem; align-items: start; margin-top: 0.8rem; }
  .people { display: grid; gap: 0.3rem; font-family: var(--font-ui); position: sticky; top: 4rem; }
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
  .old { margin: 1rem 0; font-family: var(--font-ui); }
  .old summary { cursor: pointer; font-size: 0.9rem; color: var(--ink-soft); }
  @media (max-width: 44rem) { .layout { grid-template-columns: 1fr; } .people { position: static; } }
</style>
