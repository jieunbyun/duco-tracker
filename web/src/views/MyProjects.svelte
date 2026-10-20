<script lang="ts">
  // A member's projects (they can have several), with milestones they tick off.
  import { loadMembers, loadGroupProjects, loadMilestones, loadEntries, myId } from "../lib/group";
  import type { Member, GroupProject, GroupMilestone, Entry } from "../lib/group";
  import GroupProjects from "../lib/GroupProjects.svelte";
  import { preview } from "../lib/preview.svelte";

  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let milestones = $state<GroupMilestone[]>([]);
  let entries = $state<Entry[]>([]);
  let loading = $state(true);
  let error = $state("");

  async function load() {
    try {
      const id = preview.as?.user_id ?? (await myId()); // previewing: their projects
      [members, projects, milestones, entries] = await Promise.all([loadMembers(), loadGroupProjects(), loadMilestones(), loadEntries(id)]);
      if (preview.as) projects = projects.filter((p) => p.members.includes(id) || p.lead_id === id);
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();
</script>

<section>
  <span class="eyebrow">Projects</span>
  <h1>My projects</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{:else}
    <GroupProjects {projects} {milestones} {members} {entries} supervisor={false} readonly={!!preview.as} onchanged={load} />
  {/if}
</section>
