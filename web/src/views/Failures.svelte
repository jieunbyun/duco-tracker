<script lang="ts">
  // Failures: general themes, and under each the hypotheses tried, with the test and
  // the lessons, each on a project or milestone if you like (and the way there).
  import { tick } from "svelte";
  import {
    loadBoard, saveTheme, deleteTheme, deleteFailure, placeOf, planningHash, membersHash, failuresHash, safeBack, memberFor,
  } from "../lib/failures";
  import type { Board, Theme, Failure, Attachment, World, Place } from "../lib/failures";
  import { loadProjects, loadTaxonomy } from "../lib/data";
  import type { Taxonomy } from "../lib/data";
  import { loadGroupProjects, loadMilestones, loadMembers, myId } from "../lib/group";
  import type { Member } from "../lib/group";
  import { undoable } from "../lib/undo.svelte";
  import { fmtDay, today } from "../lib/dates";
  import Linked from "../lib/Linked.svelte";
  import BackLink from "../lib/BackLink.svelte";
  import FailureForm from "../lib/FailureForm.svelte";

  // #/failures?f=<hypothesis>&back=…  or  ?new=1&p=&m=&g=&gm=&back=…  (from Planning or Members)
  const arrived = new URLSearchParams(location.hash.split("?")[1] ?? "");
  const back = safeBack(arrived.get("back"));
  if (arrived.size) history.replaceState(null, "", "#/failures");

  let board = $state<Board | null>(null);
  let world = $state<World>({ planning: [], shared: [], sharedMilestones: [] });
  let tax = $state<Taxonomy | null>(null);
  let members = $state<Member[]>([]);
  let me = $state("");
  let loading = $state(true);
  let error = $state("");
  let target = $state<string | null>(null); // lit up for a moment

  // one form at a time, so there is only ever one Delete in sight
  type Editing =
    | { kind: "theme"; id: string | null }
    | { kind: "failure"; id: string }
    | { kind: "new"; theme: string | null; attach?: Attachment };
  let editing = $state<Editing | null>(null);
  let themeName = $state("");
  let busy = $state(false);

  async function load() {
    try {
      const b = await loadBoard();
      if (b) {
        const [planning, shared, sharedMilestones, t, m, id] = await Promise.all([
          loadProjects(), loadGroupProjects(true), loadMilestones(), loadTaxonomy(), loadMembers(), myId(),
        ]);
        [world, tax, members, me] = [{ planning, shared, sharedMilestones }, t, m, id];
      }
      board = b;
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load().then(arrive);

  async function reveal(selector: string, block: ScrollLogicalPosition) {
    await tick();
    document.querySelector(selector)?.scrollIntoView({ block, behavior: "smooth" });
  }
  async function arrive() {
    if (!board || !tax) return;
    const f = arrived.get("f");
    if (f && board.items.some((x) => x.id === f)) {
      target = f;
      await reveal(`[id="fail-${f}"]`, "center");
    } else if (arrived.get("new")) {
      await openNew(null, {
        project_id: arrived.get("p"), milestone_id: arrived.get("m"),
        group_project_id: arrived.get("g"), group_milestone_id: arrived.get("gm"),
      });
    }
  }

  async function openNew(theme: string | null, attach?: Attachment) {
    editing = { kind: "new", theme, attach };
    await reveal(".failure-form", "nearest");
    document.querySelector<HTMLTextAreaElement>('.failure-form [name="hypothesis"]')?.focus({ preventScroll: true });
  }
  async function editTheme(t: Theme | null) {
    editing = { kind: "theme", id: t?.id ?? null };
    themeName = t?.name ?? "";
    await tick();
    document.querySelector<HTMLInputElement>(".theme-form input")?.focus();
  }
  async function saved(id: string) {
    await load();
    editing = null;
    target = id;
    await reveal(`[id="fail-${id}"]`, "nearest");
  }
  async function change(label: string, run: () => Promise<unknown>) {
    busy = true;
    try {
      await undoable(label, run);
      editing = null;
      await load();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
  function submitTheme(ev: SubmitEvent, t: Theme | null) {
    ev.preventDefault();
    const name = themeName.trim();
    if (name) change(t ? "Renamed theme" : "Added theme", () => saveTheme(t?.id ?? null, name));
  }
  function removeTheme(t: Theme) {
    if (confirm(`Delete the theme “${t.name}”?`)) change("Deleted theme", () => deleteTheme(t.id));
  }
  function removeFailure(f: Failure) {
    const short = f.hypothesis.length > 120 ? `${f.hypothesis.slice(0, 120)}…` : f.hypothesis;
    if (confirm(`Delete the hypothesis “${short}”?`)) change("Deleted hypothesis", () => deleteFailure(f.id));
  }

  function whereOf(at: Place): string | null {
    const name = at.project?.name ?? at.group?.title;
    if (!name) return null;
    const ms = at.milestone?.title ?? at.groupMilestone?.title;
    return `${name}${ms ? ` › ${ms}` : ""}${!at.project && at.group?.deleted_at ? " (in the bin)" : ""}`;
  }
  const isLinked = (f: Failure) => !!(f.project_id || f.milestone_id || f.group_project_id || f.group_milestone_id);
  function go(f: Failure, to: string) {
    history.replaceState(null, "", failuresHash(f.id, back)); // so the browser's Back lands on it too
    location.hash = to;
  }
</script>

{#snippet themeForm(t: Theme | null, empty: boolean)}
  <form class="theme-form" onsubmit={(e) => submitTheme(e, t)}>
    <label>Theme <input bind:value={themeName} required placeholder="A general theme, e.g. Surrogate modelling" /></label>
    <button class="primary" type="submit" disabled={busy}>{t ? "Save" : "Add theme"}</button>
    <button type="button" onclick={() => (editing = null)} disabled={busy}>Cancel</button>
    {#if t}
      {#if empty}
        <button type="button" class="danger" onclick={() => removeTheme(t)} disabled={busy}>Delete theme</button>
      {:else}
        <span class="hint">A theme can be deleted once it has no hypotheses.</span>
      {/if}
    {/if}
  </form>
{/snippet}

{#snippet newForm(theme: string | null, attach?: Attachment)}
  {#if board && tax}
    <FailureForm failure={null} themeId={theme} {attach} themes={board.themes} {world} {tax}
                 onsaved={saved} oncancel={() => (editing = null)} />
  {/if}
{/snippet}

<section>
  <span class="eyebrow">Failures</span>
  <h1>Failures</h1>
  <p class="muted intro">Hypotheses by theme: how each was tested, and what its failure taught you. Only you see them.</p>
  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if board && tax}
    <div class="bar">
      <button class="primary" onclick={() => openNew(null)} disabled={!!editing}>+ Hypothesis</button>
      <button onclick={() => editTheme(null)} disabled={!!editing}>+ Theme</button>
    </div>
    {#if editing?.kind === "theme" && editing.id === null}{@render themeForm(null, true)}{/if}
    {#if editing?.kind === "new" && editing.theme === null}{@render newForm(null, editing.attach)}{/if}

    {#each board.themes as t (t.id)}
      {@const items = board.items.filter((f) => f.theme_id === t.id)}
      <section class="theme">
        {#if editing?.kind === "theme" && editing.id === t.id}
          {@render themeForm(t, !items.length)}
        {:else}
          <header>
            <h2>{t.name}</h2>
            <span class="muted count">{items.length} {items.length === 1 ? "hypothesis" : "hypotheses"}</span>
            <span class="spacer"></span>
            <button class="mini" onclick={() => openNew(t.id)} disabled={!!editing}>+ Hypothesis</button>
            <button class="mini" onclick={() => editTheme(t)} disabled={!!editing}>Edit theme</button>
          </header>
        {/if}
        {#if editing?.kind === "new" && editing.theme === t.id}{@render newForm(t.id)}{/if}

        {#each items as f (f.id)}
          {#if editing?.kind === "failure" && editing.id === f.id}
            <FailureForm failure={f} themes={board.themes} {world} {tax} onsaved={saved}
                         oncancel={() => (editing = null)} ondelete={() => removeFailure(f)} />
          {:else}
            {@const at = placeOf(f, world)}
            {@const where = whereOf(at)}
            {@const member = at.group && !at.group.deleted_at ? memberFor(at.group, me, members) : null}
            <article class="card" id={`fail-${f.id}`} class:target={target === f.id}>
              <div class="top">
                <h3><Linked text={f.hypothesis} /></h3>
                <button class="mini" onclick={() => (editing = { kind: "failure", id: f.id })} disabled={!!editing}>Edit</button>
              </div>
              <dl>
                <dt>Test</dt>
                <dd class:blank={!f.test}>{#if f.test}<Linked text={f.test} />{:else}Not written yet{/if}</dd>
                <dt>Lessons from failure</dt>
                <dd class:blank={!f.lesson}>{#if f.lesson}<Linked text={f.lesson} />{:else}Not written yet{/if}</dd>
              </dl>
              <footer>
                <span>Created {fmtDay(f.created_on)}</span>
                {#if f.due_on}
                  {@const late = !f.lesson && f.due_on < today()}
                  <span class:overdue={late}>Deadline {fmtDay(f.due_on)}{late ? " · overdue" : ""}</span>
                {/if}
                {#if where}<span class="where">{where}</span>{:else if isLinked(f)}<span>Its project was deleted</span>{/if}
                <span class="spacer"></span>
                {#if at.project}
                  <button class="mini" onclick={() => go(f, planningHash(at.project!.id, at.milestone?.id, f.id))}
                          disabled={!!editing}>Open in Planning ›</button>
                {/if}
                {#if at.group && member}
                  <button class="mini" onclick={() => go(f, membersHash(member, at.group!.id, at.groupMilestone?.id, f.id))}
                          disabled={!!editing}>Open in Members ›</button>
                {/if}
              </footer>
            </article>
          {/if}
        {:else}
          <p class="muted empty">No hypotheses yet.</p>
        {/each}
      </section>
    {:else}
      {#if !editing}<p class="muted">No themes yet. Start with + Theme, or + Hypothesis and name its theme there.</p>{/if}
    {/each}
  {:else if !error}
    <p class="muted">Failures needs its tables first: run <code>web/db/0052_failures.sql</code> in the Supabase SQL editor, then reload.</p>
  {/if}
</section>

{#if back}
  <BackLink href={back} text={back.startsWith("#/planning") ? "Back to Planning" : "Back to Members"} />
{/if}

<style>
  .intro { font-size: 0.9rem; max-width: 46rem; }
  .bar, header, .top, footer, .theme-form { display: flex; flex-wrap: wrap; gap: 0.4rem 0.6rem; font-family: var(--font-ui); }
  .bar { margin-bottom: 1rem; }
  header { align-items: baseline; border-bottom: 1px solid var(--rule); padding-bottom: 0.3rem; }
  header h2 { margin: 0; font-family: var(--font); min-width: 0; overflow-wrap: anywhere; }
  .theme { margin-top: 1.6rem; }
  .count, .hint, .empty { font-family: var(--font-ui); font-size: 0.8rem; }
  .hint { color: var(--ink-soft); padding-bottom: 0.5rem; }
  .spacer { flex: 1; }
  .theme-form { align-items: flex-end; margin: 0.5rem 0; }
  .theme-form label { display: grid; gap: 0.2rem; flex: 1 1 16rem; font-size: 0.8rem; color: var(--ink-soft); }
  .danger { color: var(--danger); }
  .card {
    border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.7rem 0.9rem; margin-top: 0.6rem;
    scroll-margin-top: 4.5rem;
  }
  .card.target { animation: lit 3s ease-out; }
  @keyframes lit { from, 40% { background: color-mix(in srgb, var(--accent) 22%, transparent); } to { background: transparent; } }
  .top { flex-wrap: nowrap; align-items: flex-start; }
  .top h3 { flex: 1; min-width: 0; margin: 0; font-family: var(--font); font-size: 1.02rem; white-space: pre-wrap; overflow-wrap: anywhere; }
  dl {
    display: grid; grid-template-columns: 10rem minmax(0, 1fr); gap: 0.3rem 0.8rem; margin: 0.5rem 0;
    font-family: var(--font-ui); font-size: 0.88rem;
  }
  dt { color: var(--ink-soft); }
  dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  dd.blank { color: var(--ink-soft); font-style: italic; }
  footer { align-items: baseline; font-size: 0.78rem; color: var(--ink-soft); }
  .where { color: var(--ink); min-width: 0; overflow-wrap: anywhere; }
  .overdue { color: var(--danger); }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; white-space: nowrap; }
  @media (max-width: 40rem) { dl { grid-template-columns: minmax(0, 1fr); } }
</style>
