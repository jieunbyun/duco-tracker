<script lang="ts">
  // A member's projects (they can have several), with milestones they tick off.
  import { loadMembers, loadGroupProjects, loadMilestones, myId } from "../lib/group";
  import type { Member, GroupProject, GroupMilestone } from "../lib/group";
  import { loadProjectActivity } from "../lib/actions";
  import GroupProjects from "../lib/GroupProjects.svelte";
  import { preview } from "../lib/preview.svelte";

  let members = $state<Member[]>([]);
  let projects = $state<GroupProject[]>([]);
  let milestones = $state<GroupMilestone[]>([]);
  let activity = $state(new Map<string, number>());
  let loading = $state(true);
  let error = $state("");

  async function load() {
    try {
      const id = preview.as?.user_id ?? (await myId()); // previewing: their projects
      const week = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
      [members, projects, milestones, activity] = await Promise.all([loadMembers(), loadGroupProjects(), loadMilestones(), loadProjectActivity(week)]);
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
  {#if preview.as}
    <p class="muted small">Preview: read-only here. {preview.as.display_name} can click a milestone (✎) to edit it — dates,
      what it comes after, lead, notes — tick it done, and add one with + Milestone.</p>
  {/if}
  {#if loading}<p class="muted">Loading…</p>{:else}
    <GroupProjects {projects} {milestones} {members} {activity} supervisor={false} readonly={!!preview.as} onchanged={load} />
  {/if}
</section>
