<script lang="ts">
  // A student's projects (they can have several), with milestones they tick off.
  import { loadMembers, loadGroupProjects, loadMilestones, loadEntries, myId } from "../lib/group";
  import type { Member, GroupProject, GroupMilestone, Entry } from "../lib/group";
  import GroupProjects from "../lib/GroupProjects.svelte";

  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let milestones = $state<GroupMilestone[]>([]);
  let entries = $state<Entry[]>([]);
  let loading = $state(true);
  let error = $state("");

  async function load() {
    try {
      const id = await myId();
      [members, projects, milestones, entries] = await Promise.all([loadMembers(), loadGroupProjects(), loadMilestones(), loadEntries(id)]);
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
    <GroupProjects {projects} {milestones} {members} {entries} supervisor={false} onchanged={load} />
  {/if}
</section>
