<script lang="ts">
  // One hypothesis, new or edited: what it is, its theme, and what it is on.
  import { untrack } from "svelte";
  import { saveFailure, saveTheme, placeOf, NOWHERE } from "./failures";
  import type { Theme, Failure, Attachment, World } from "./failures";
  import type { Taxonomy } from "./data";
  import { planningGroups } from "./group";
  import { undoable } from "./undo.svelte";
  import { today } from "./dates";

  type Props = {
    failure: Failure | null; // null: a new one
    themeId?: string | null; // a new one's theme
    attach?: Attachment; // what a new one starts on
    themes: Theme[];
    world: World;
    tax: Taxonomy;
    onsaved: (id: string) => void;
    oncancel: () => void;
    ondelete?: () => void;
  };
  let { failure, themeId = null, attach = NOWHERE, themes, world, tax, onsaved, oncancel, ondelete }: Props = $props();

  const NEW = "new";
  const KEEP = "keep"; // what it was on is out of sight (deleted, or no longer visible)
  const f0 = untrack(() => failure);
  const on0: Attachment = untrack(() => f0 ?? attach);
  const at = untrack(() => placeOf(on0, world));
  const linked0 = !!(on0.project_id || on0.milestone_id || on0.group_project_id || on0.group_milestone_id);
  const project0 = at.project ? `p:${at.project.id}` : at.group ? `g:${at.group.id}` : linked0 ? KEEP : "";
  const milestone0 = (at.project ? at.milestone?.id : at.groupMilestone?.id) ?? "";

  let hypothesis = $state(f0?.hypothesis ?? "");
  let test = $state(f0?.test ?? "");
  let lesson = $state(f0?.lesson ?? "");
  let created_on = $state(f0?.created_on ?? today());
  let due_on = $state(f0?.due_on ?? "");
  let theme = $state(f0?.theme_id ?? untrack(() => themeId ?? (themes.length ? "" : NEW)));
  let themeName = $state("");
  let project = $state(project0);
  let milestone = $state(milestone0);
  let busy = $state(false);
  let error = $state("");

  // Planning's projects by area and category; then shared ones no Planning project stands for.
  const groups = $derived.by(() => {
    const cat = new Map(tax.allCategories.map((c, i) => [c.id, { c, i }]));
    const area = new Map(tax.areas.map((a, i) => [a.id, { a, i }]));
    const refs = world.planning.map((p) => {
      const c = cat.get(p.category_id);
      const a = c && area.get(c.c.area_id);
      return {
        id: p.id, milestones: [], order: (a?.i ?? 999) * 1000 + (c?.i ?? 999),
        name: p.status === "active" ? p.name : `${p.name} (${p.status})`,
        group: `${a?.a.label ?? "Other"} › ${c?.c.label ?? "—"}`,
      };
    });
    return planningGroups(refs.sort((x, y) => x.order - y.order || x.name.localeCompare(y.name)));
  });
  const sharedOnly = $derived(world.shared.filter((g) =>
    (!g.deleted_at && !world.planning.some((p) => p.group_project_id === g.id)) || project0 === `g:${g.id}`));
  const milestones = $derived(
    project.startsWith("p:") ? (world.planning.find((p) => p.id === project.slice(2))?.milestone ?? [])
    : project.startsWith("g:") ? world.sharedMilestones.filter((m) => m.project_id === project.slice(2))
    : [],
  );

  function attachment(): Attachment {
    // unchanged: exactly as stored, so a link to something in the bin survives an edit
    if (project === KEEP || (f0 && project === project0 && milestone === milestone0)) {
      const { project_id, milestone_id, group_project_id, group_milestone_id } = on0;
      return { project_id, milestone_id, group_project_id, group_milestone_id };
    }
    const id = project.slice(2);
    const m = milestone || null;
    return project.startsWith("p:") ? { ...NOWHERE, project_id: id, milestone_id: m }
      : project.startsWith("g:") ? { ...NOWHERE, group_project_id: id, group_milestone_id: m }
      : NOWHERE;
  }

  async function save(ev: SubmitEvent) {
    ev.preventDefault();
    if (!hypothesis.trim()) return (error = "Write the hypothesis.");
    if (!theme || (theme === NEW && !themeName.trim())) return (error = "Give it a theme.");
    if (due_on && due_on < created_on) return (error = "The deadline is before the creation date.");
    busy = true;
    error = "";
    try {
      const id = await undoable(f0 ? "Changed hypothesis" : "Added hypothesis", async () => {
        const theme_id = theme === NEW ? await saveTheme(null, themeName.trim()) : theme;
        return saveFailure(f0?.id ?? null, {
          theme_id, hypothesis: hypothesis.trim(), test: test.trim() || null, lesson: lesson.trim() || null,
          created_on, due_on: due_on || null, ...attachment(),
        });
      });
      onsaved(id);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
</script>

<form class="failure-form" onsubmit={save}>
  <label class="wide">Hypothesis
    <textarea name="hypothesis" rows="2" bind:value={hypothesis} required placeholder="What you expected to be true"></textarea>
  </label>
  <label class="wide">Test
    <textarea name="test" rows="3" bind:value={test} placeholder="How you test it, and what would count as failure"></textarea>
  </label>
  <label class="wide">Lessons from failure
    <textarea name="lesson" rows="3" bind:value={lesson} placeholder="What happened, and what you learnt"></textarea>
  </label>
  <label>Theme
    <select name="theme" bind:value={theme} required>
      <option value="" disabled>Choose a theme…</option>
      {#each themes as t (t.id)}<option value={t.id}>{t.name}</option>{/each}
      <option value={NEW}>+ New theme…</option>
    </select>
  </label>
  <label>Created <input name="created_on" type="date" bind:value={created_on} required /></label>
  <label>Deadline <input name="due_on" type="date" bind:value={due_on} min={created_on || undefined} /></label>
  {#if theme === NEW}
    <label class="wide">New theme
      <input name="theme_name" bind:value={themeName} required placeholder="A general theme, e.g. Surrogate modelling" />
    </label>
  {/if}
  <label class="span2">Project (optional)
    <select name="project" bind:value={project} onchange={() => (milestone = "")}>
      <option value="">— none —</option>
      {#if project0 === KEEP}<option value={KEEP}>(deleted or out of sight: keep the link)</option>{/if}
      {#each groups as g (g.label)}
        <optgroup label={g.label}>{#each g.items as p (p.id)}<option value={`p:${p.id}`}>{p.name}</option>{/each}</optgroup>
      {/each}
      {#if sharedOnly.length}
        <optgroup label="Shared projects">{#each sharedOnly as g (g.id)}<option value={`g:${g.id}`}>{g.title}</option>{/each}</optgroup>
      {/if}
    </select>
  </label>
  <label>Milestone (optional)
    <select name="milestone" bind:value={milestone} disabled={!milestones.length}>
      <option value="">— the project as a whole —</option>
      {#each milestones as m (m.id)}<option value={m.id}>{m.title}</option>{/each}
    </select>
  </label>
  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{f0 ? "Save" : "Add hypothesis"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if ondelete}<button type="button" class="danger" onclick={ondelete} disabled={busy}>Delete hypothesis</button>{/if}
  </div>
</form>

<style>
  .failure-form {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem 0.9rem; font-family: var(--font-ui);
    background: var(--panel); border-radius: var(--radius); padding: 0.8rem; margin: 0.5rem 0; scroll-margin-top: 4.5rem;
  }
  label { display: grid; gap: 0.2rem; align-content: start; font-size: 0.8rem; color: var(--ink-soft); min-width: 0; }
  .wide { grid-column: 1 / -1; }
  .span2 { grid-column: span 2; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
  @media (max-width: 40rem) {
    .failure-form { grid-template-columns: minmax(0, 1fr); }
    .span2 { grid-column: auto; }
  }
</style>
