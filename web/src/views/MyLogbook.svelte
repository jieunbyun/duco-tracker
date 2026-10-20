<script lang="ts">
  // A logbook of one's own: what they did, results and next steps, with links to
  // their files on OneDrive. A member's supervisor reads it and comments; the
  // supervisor's own is for the projects they lead.
  import {
    loadMembers, loadGroupProjects, loadEntries, loadComments, revisionCounts, logbookMarkdown, download, myId, loadMilestones,
  } from "../lib/group";
  import type { Member, GroupProject, GroupMilestone, Entry, Comment, PlanningRef } from "../lib/group";
  import { loadProjects } from "../lib/data";
  import { LIVE_STATUSES } from "../lib/plan";
  import Logbook from "../lib/Logbook.svelte";
  import { preview } from "../lib/preview.svelte";

  let me = $state("");
  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let entries = $state<Entry[]>([]);
  let comments = $state<Comment[]>([]);
  let edits = $state(new Map<string, number>());
  let loading = $state(true);
  let error = $state("");
  let filter = $state(""); // "g:<id>" a shared project, "p:<id>" a Planning one, or "" for all
  let planning = $state<PlanningRef[]>([]); // your own Planning projects, when the logbook is yours
  let groupMilestones = $state<GroupMilestone[]>([]);

  async function load() {
    try {
      const id = preview.as?.user_id ?? (await myId()); // previewing: their logbook
      const [m, p, es] = await Promise.all([loadMembers(), loadGroupProjects(), loadEntries(id)]);
      const ids = es.map((e) => e.id);
      const [cs, ed] = await Promise.all([loadComments(ids), revisionCounts(ids)]);
      [me, members, projects, entries, comments, edits] = [id, m, p, es, cs, ed];
      groupMilestones = await loadMilestones().catch(() => []);
      // your own Planning projects can have logbook notes too (only the planner's owner has any)
      if (!preview.as && m.find((x) => x.user_id === id)?.role === "supervisor") {
        const used = new Set(es.map((e) => e.planning_project_id).filter(Boolean));
        planning = (await loadProjects())
          .filter((x) => LIVE_STATUSES.has(x.status) || used.has(x.id))
          .map((x) => ({ id: x.id, name: x.name, milestones: x.milestone.map((m) => ({ id: m.id, title: m.title })) }));
      }
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  const shown = $derived(
    !filter ? entries
      : filter.startsWith("p:") ? entries.filter((e) => e.planning_project_id === filter.slice(2))
      : entries.filter((e) => e.project_id === filter.slice(2)),
  );
  const myName = $derived(members.find((m) => m.user_id === me)?.display_name ?? "me");
  // yours first: the projects you lead or are on
  const ordered = $derived([
    ...projects.filter((p) => p.lead_id === me || p.members.includes(me)),
    ...projects.filter((p) => !(p.lead_id === me || p.members.includes(me))),
  ]);
  function exportMine() {
    download(`logbook-${new Date().toISOString().slice(0, 10)}.md`,
      logbookMarkdown(entries, projects, members, comments, edits, `Logbook — ${myName}`, planning, groupMilestones));
  }
</script>

<section>
  <span class="eyebrow">Logbook</span>
  <h1>Logbook</h1>
  <p class="muted intro">
    A few lines a day and links to the files on OneDrive.
  </p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{:else}
    <div class="bar">
      <label class="small">Show
        <select bind:value={filter}>
          <option value="">all projects</option>
          {#if planning.length && ordered.length}<optgroup label="Shared projects">{#each ordered as p (p.id)}<option value={`g:${p.id}`}>{p.title}</option>{/each}</optgroup>
          {:else}{#each ordered as p (p.id)}<option value={`g:${p.id}`}>{p.title}</option>{/each}{/if}
          {#if planning.length}<optgroup label="My projects (Planning)">{#each planning as p (p.id)}<option value={`p:${p.id}`}>{p.name}</option>{/each}</optgroup>{/if}
        </select>
      </label>
      <span class="spacer"></span>
      <button class="mini" onclick={exportMine} disabled={!entries.length} title="As a Markdown file, to keep on OneDrive">Export my logbook</button>
    </div>
    <Logbook entries={shown} projects={ordered} {planning} {groupMilestones} {members} {comments} {edits} {me} canWrite={!preview.as} onchanged={load} />
  {/if}
</section>

<style>
  .intro { max-width: 46rem; font-size: 0.9rem; }
  .bar { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin: 0.6rem 0; font-family: var(--font-ui); }
  .bar select { width: auto; }
  .spacer { flex: 1; }
  .mini { font-size: 0.8rem; padding: 0.25rem 0.7rem; }
  .small { font-size: 0.85rem; }
</style>
