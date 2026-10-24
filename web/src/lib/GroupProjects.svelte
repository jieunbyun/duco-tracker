<script lang="ts">
  import {
    saveGroupProject, startGroupProject, deleteGroupProject, addProjectMember, removeProjectMember,
  } from "./group";
  import type { GroupProject, GroupMilestone, Member } from "./group";
  import { fromMonth, fmtMonth } from "./pathways";
  import { today } from "./dates";
  import FolderLink from "./FolderLink.svelte";
  import GroupMilestones from "./GroupMilestones.svelte";

  type Props = {
    projects: GroupProject[];
    milestones: GroupMilestone[];
    members: Member[];
    activity?: Map<string, number>; // comments on each project's actions this week
    supervisor: boolean; // you: takes people off projects and deletes them (everyone starts projects and adds collaborators)
    newFor?: string | null; // when set, "+ Project" puts this person on the new project
    readonly?: boolean; // previewing what a member sees
    onchanged: () => Promise<void>;
  };
  let { projects, milestones, members, activity = new Map(), supervisor, newFor = null, readonly = false, onchanged }: Props = $props();

  let error = $state("");
  /** Run a change and reload; false (with the message shown) if it failed. */
  const act = async (f: () => Promise<unknown>): Promise<boolean> => {
    try { error = ""; await f(); await onchanged(); return true; } catch (e) { error = (e as Error).message; return false; }
  };
  const nameOf = (id: string) => members.find((m) => m.user_id === id)?.display_name ?? "—";
  const assignable = $derived(members.filter((m) => m.active));

  // ---- a project's details (new or edited) ------------------------------------------
  // Everyone on a project is a collaborator: no lead is set here (one set earlier is kept, unseen).
  type Draft = { id: string | null; title: string; aim: string; status: GroupProject["status"]; start: string; end: string; folder: string };
  let draft = $state<Draft | null>(null);
  function edit(p: GroupProject | null) {
    draft = p
      ? { id: p.id, title: p.title, aim: p.aim ?? "", status: p.status, start: (p.start_on ?? "").slice(0, 7), end: (p.end_on ?? "").slice(0, 7), folder: p.folder_url ?? "" }
      : { id: null, title: "", aim: "", status: "active", start: today().slice(0, 7), end: "", folder: "" };
  }
  async function saveDraft(ev: SubmitEvent) {
    ev.preventDefault();
    const d = draft;
    if (!d || !d.title.trim()) return;
    const was = d.id ? projects.find((p) => p.id === d.id) : null;
    const fields = {
      title: d.title.trim(), aim: d.aim.trim() || null, status: d.status,
      start_on: fromMonth(d.start, false, was?.start_on ?? null), end_on: fromMonth(d.end, true, was?.end_on ?? null),
    };
    await act(async () => {
      if (!d.id && !supervisor) {
        // a member starts one: they are on it from the start
        await startGroupProject({ ...fields, folder_url: d.folder.trim() || null });
      } else {
        const id = await saveGroupProject(d.id, {
          ...fields, ...(d.folder.trim() || was?.folder_url ? { folder_url: d.folder.trim() || null } : {}),
        });
        if (!d.id && newFor) await addProjectMember(id, newFor);
      }
      draft = null;
    });
  }

</script>

{#if error}<p class="error">{error}</p>{/if}
{#if !readonly && !draft}<button class="add" onclick={() => edit(null)}>+ Project</button>{/if}

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
      <label class="wide">OneDrive folder (link) <input type="url" bind:value={draft.folder} placeholder="https://…sharepoint.com/…" /></label>
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
        <h3>{p.title}<FolderLink url={p.folder_url} /></h3>
        <span class="muted small">
          {p.status}{p.start_on ? ` · ${fmtMonth(p.start_on)} → ${p.end_on ? fmtMonth(p.end_on) : "…"}` : ""}
          · {activity.get(p.id) ?? 0} {(activity.get(p.id) ?? 0) === 1 ? "comment" : "comments"} this week
        </span>
        <span class="spacer"></span>
        {#if !readonly}<button class="mini" onclick={() => edit(p)}>Edit</button>{/if}
        {#if supervisor}
          <button class="mini danger" onclick={() => confirm(`Delete the project “${p.title}”? Its collaborators' actions stay, without a project.`) && act(() => deleteGroupProject(p.id))}>Delete</button>
        {/if}
      </header>
      {#if p.aim}<p class="aim">{p.aim}</p>{/if}
    {/if}

    <div class="people small">
      <span class="muted">Collaborators:</span>
      {#each p.members as uid (uid)}
        <span class="person">{nameOf(uid)}{#if supervisor}<button class="x" aria-label="Take off the project" onclick={() => act(() => removeProjectMember(p.id, uid))}>✕</button>{/if}</span>
      {:else}<span class="muted">nobody yet</span>{/each}
      {#if !readonly}
        <!-- any collaborator adds others; only you take people off -->
        {@const others = assignable.filter((s) => !p.members.includes(s.user_id))}
        {#if others.length}
          <select aria-label="Add someone" onchange={(ev) => { const v = (ev.target as HTMLSelectElement).value; if (v) act(() => addProjectMember(p.id, v)); }}>
            <option value="">+ add a collaborator…</option>
            {#each others as s (s.user_id)}<option value={s.user_id}>{s.display_name}</option>{/each}
          </select>
        {/if}
      {/if}
    </div>

    <GroupMilestones project={p} milestones={ms} {readonly} {act} />
  </section>
{:else}
  <p class="muted">{readonly ? "No projects yet." : "No projects yet: start one with + Project."}</p>
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
