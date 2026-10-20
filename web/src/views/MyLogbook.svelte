<script lang="ts">
  // A logbook of one's own: what they did, results and next steps, with links to
  // their files on OneDrive. A member's supervisor reads it and comments; the
  // supervisor's own is for the projects they lead.
  import {
    loadMembers, loadGroupProjects, loadEntries, loadComments, revisionCounts, logbookMarkdown, download, myId,
  } from "../lib/group";
  import type { Member, GroupProject, Entry, Comment } from "../lib/group";
  import Logbook from "../lib/Logbook.svelte";

  let me = $state("");
  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let entries = $state<Entry[]>([]);
  let comments = $state<Comment[]>([]);
  let edits = $state(new Map<string, number>());
  let loading = $state(true);
  let error = $state("");
  let filter = $state(""); // a project id, or "" for all

  async function load() {
    try {
      const id = await myId();
      const [m, p, es] = await Promise.all([loadMembers(), loadGroupProjects(), loadEntries(id)]);
      const ids = es.map((e) => e.id);
      const [cs, ed] = await Promise.all([loadComments(ids), revisionCounts(ids)]);
      [me, members, projects, entries, comments, edits] = [id, m, p, es, cs, ed];
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  const shown = $derived(filter ? entries.filter((e) => e.project_id === filter) : entries);
  const myName = $derived(members.find((m) => m.user_id === me)?.display_name ?? "me");
  const supervisor = $derived(members.find((m) => m.user_id === me)?.role === "supervisor");
  // yours first: the projects you lead or are on
  const ordered = $derived([
    ...projects.filter((p) => p.lead_id === me || p.members.includes(me)),
    ...projects.filter((p) => !(p.lead_id === me || p.members.includes(me))),
  ]);
  function exportMine() {
    download(`logbook-${new Date().toISOString().slice(0, 10)}.md`,
      logbookMarkdown(entries, projects, members, comments, edits, `Logbook — ${myName}`));
  }
</script>

<section>
  <span class="eyebrow">Logbook</span>
  <h1>Logbook</h1>
  <p class="muted intro">
    A few lines a day: what you did, what came of it, what's next — and links to the files on OneDrive.
    {#if supervisor}This one is yours, for the projects you lead; members don't see it.
    {:else}Your supervisor reads it and comments; nobody else in the group sees it.{/if}
    You can edit any entry (the earlier version is kept in its history) and delete one on the day you wrote it.
  </p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{:else}
    <div class="bar">
      <label class="small">Show
        <select bind:value={filter}>
          <option value="">all projects</option>
          {#each ordered as p (p.id)}<option value={p.id}>{p.title}</option>{/each}
        </select>
      </label>
      <span class="spacer"></span>
      <button class="mini" onclick={exportMine} disabled={!entries.length} title="As a Markdown file, to keep on OneDrive">Export my logbook</button>
    </div>
    <Logbook entries={shown} projects={ordered} {members} {comments} {edits} {me} canWrite onchanged={load} />
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
