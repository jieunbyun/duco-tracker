<script lang="ts">
  // The Logbook, built on actions: each project's actions by milestone, each with
  // its dated thread of comments and links. A member's supervisor reads it and
  // replies; the supervisor's own covers the projects they lead and their
  // Planning projects. Entries written before the Logbook moved to actions stay
  // readable at the bottom.
  import {
    loadMembers, loadGroupProjects, loadEntries, loadComments, revisionCounts, logbookMarkdown, download, myId, loadMilestones,
    planningGroups,
  } from "../lib/group";
  import type { Member, GroupProject, GroupMilestone, Entry, Comment, PlanningRef } from "../lib/group";
  import { loadProjects, loadTaxonomy } from "../lib/data";
  import { LIVE_STATUSES } from "../lib/plan";
  import Logbook from "../lib/Logbook.svelte";
  import ActionLog from "../lib/ActionLog.svelte";
  import ActionHistory from "../lib/ActionHistory.svelte";
  import { loadMyActions, loadSharedActions, loadMemberActions, loadDoneActions, loadActionComments, actionsMarkdown } from "../lib/actions";
  import type { Action, ActionComment } from "../lib/actions";
  import { preview } from "../lib/preview.svelte";

  let me = $state("");
  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let groupMilestones = $state<GroupMilestone[]>([]);
  let planning = $state<PlanningRef[]>([]); // your own Planning projects, when the logbook is yours
  let actions = $state<Action[]>([]);
  let thread = $state<ActionComment[]>([]);
  let entries = $state<Entry[]>([]); // written before the Logbook moved to actions
  let comments = $state<Comment[]>([]);
  let edits = $state(new Map<string, number>());
  let loading = $state(true);
  let error = $state("");
  let filter = $state(""); // "g:<id>" a shared project, "p:<id>" a Planning one, or "" for all

  async function load() {
    try {
      const id = preview.as?.user_id ?? (await myId()); // previewing: their logbook
      const [m, p, ms, acts, es] = await Promise.all([
        loadMembers(), loadGroupProjects(), loadMilestones().catch(() => [] as GroupMilestone[]),
        // yours, and everyone else's on public milestones of your shared projects (read-only)
        preview.as ? loadMemberActions(id) : Promise.all([loadMyActions(), loadSharedActions()]).then(([a, b]) => [...a, ...b]),
        loadEntries(id).catch(() => [] as Entry[]),
      ]);
      const [th, cs, ed] = await Promise.all([
        loadActionComments(acts.map((a) => a.id)), loadComments(es.map((e) => e.id)), revisionCounts(es.map((e) => e.id)),
      ]);
      [me, members, projects, groupMilestones, actions, thread, entries, comments, edits] = [id, m, p, ms, acts, th, es, cs, ed];
      // previewing: only their projects, as they see them (you see every project)
      if (preview.as) projects = p.filter((x) => x.members.includes(id) || x.lead_id === id);
      // your own Planning projects have actions too (only the planner's owner has any)
      if (!preview.as && m.find((x) => x.user_id === id)?.role === "supervisor") {
        const used = new Set(acts.map((a) => a.project_id).filter(Boolean));
        const [all, tax] = await Promise.all([loadProjects(), loadTaxonomy()]);
        // listed by area and category, in Planning's order, so a project is easy to find
        const cat = new Map(tax.allCategories.map((c) => [c.id, c]));
        const area = new Map(tax.areas.map((a) => [a.id, a]));
        const where = (x: { category_id: string }) => {
          const c = cat.get(x.category_id), a = c ? area.get(c.area_id) : undefined;
          return { label: `${a?.label ?? "Other"} › ${c?.label ?? "—"}`, order: [a?.sort_order ?? 999, c?.sort_order ?? 999] };
        };
        planning = all
          .filter((x) => LIVE_STATUSES.has(x.status) || used.has(x.id))
          .sort((x, y) => where(x).order[0] - where(y).order[0] || where(x).order[1] - where(y).order[1] || x.name.localeCompare(y.name))
          .map((x) => ({ id: x.id, name: x.name, category_id: x.category_id, group: where(x).label,
                         milestones: x.milestone.map((ms) => ({ id: ms.id, title: ms.title, active: ms.status === "active" })) }));
      }
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  const myName = $derived(members.find((m) => m.user_id === me)?.display_name ?? "me");
  // yours first: the projects you lead or are on
  const ordered = $derived([
    ...projects.filter((p) => p.lead_id === me || p.members.includes(me)),
    ...projects.filter((p) => !(p.lead_id === me || p.members.includes(me))),
  ]);
  const oldShown = $derived(
    !filter ? entries
      : filter.startsWith("p:") ? entries.filter((e) => e.planning_project_id === filter.slice(2))
      : entries.filter((e) => e.project_id === filter.slice(2)),
  );

  function whereOf(a: Action): string {
    if (a.project_id) {
      const p = planning.find((x) => x.id === a.project_id);
      const m = p?.milestones.find((x) => x.id === a.milestone_id);
      return `${p?.name ?? "Planning project"}${m ? ` › ${m.title}` : ""}`;
    }
    const m = groupMilestones.find((x) => x.id === a.group_milestone_id);
    return `${projects.find((x) => x.id === a.group_project_id)?.title ?? "Shared project"}${m ? ` › ${m.title}` : ""}`;
  }
  async function exportMine() {
    // everything: open actions, and all those done, each with its thread
    const done = preview.as ? [] : await loadDoneActions();
    const every = [...actions.filter((a) => !a.is_done), ...done, ...(preview.as ? actions.filter((a) => a.is_done) : [])];
    const th = await loadActionComments(every.map((a) => a.id));
    const nameOf = (uid: string) => members.find((m) => m.user_id === uid)?.display_name ?? "—";
    let text = actionsMarkdown(every, th, `Logbook — ${myName}`, whereOf, nameOf);
    if (entries.length) text += "\n\n" + logbookMarkdown(entries, projects, members, comments, edits, "Earlier entries", planning, groupMilestones);
    download(`logbook-${new Date().toISOString().slice(0, 10)}.md`, text);
  }
</script>

<section>
  <span class="eyebrow">Logbook</span>
  <h1>Logbook</h1>
  <p class="muted intro">Actions by project and milestone, each with its comments and links.</p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{:else}
    <div class="bar">
      <label class="small">Project
        <select bind:value={filter}>
          <option value="">all</option>
          {#if ordered.length}<optgroup label="Shared projects">{#each ordered as p (p.id)}<option value={`g:${p.id}`}>{p.title}</option>{/each}</optgroup>{/if}
          {#each planningGroups(planning) as g (g.label)}<optgroup label={g.label}>{#each g.items as p (p.id)}<option value={`p:${p.id}`}>{p.name}</option>{/each}</optgroup>{/each}
        </select>
      </label>
      <span class="spacer"></span>
      <button class="mini" onclick={exportMine} disabled={!actions.length && !entries.length} title="As a Markdown file, to keep on OneDrive">Export logbook</button>
    </div>
    <ActionLog {actions} comments={thread} projects={ordered} {planning} {groupMilestones} {filter} {members} {me}
               canWrite={!preview.as} canComment={!preview.as} onchanged={load} />
    <ActionHistory load={() => (preview.as ? loadMemberActions(preview.as.user_id) : loadDoneActions())}
                   projects={ordered} {planning} {groupMilestones} {members} {me} {filter} />
    {#if oldShown.length}
      <details class="old">
        <summary>Earlier entries ({oldShown.length})</summary>
        <Logbook entries={oldShown} projects={ordered} {planning} {groupMilestones} {members} {comments} {edits} {me} canWrite={false} onchanged={load} />
      </details>
    {/if}
  {/if}
</section>

<style>
  .intro { max-width: 46rem; font-size: 0.9rem; }
  .bar { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin: 0.6rem 0; font-family: var(--font-ui); }
  .bar select { width: auto; }
  .spacer { flex: 1; }
  .mini { font-size: 0.8rem; padding: 0.25rem 0.7rem; }
  .small { font-size: 0.85rem; }
  .old { margin: 1rem 0; font-family: var(--font-ui); }
  .old summary { cursor: pointer; font-size: 0.9rem; color: var(--ink-soft); }
</style>
