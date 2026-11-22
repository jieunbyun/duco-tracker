<script lang="ts">
  // Failures: general themes, and under each the hypotheses tried, with the test and
  // the lessons, each on a project or milestone if you like (and the way there).
  import { tick } from "svelte";
  import {
    loadBoard, saveTheme, deleteTheme, deleteFailure, saveFailure, placeOf, planningHash, membersHash, failuresHash, safeBack,
    memberFor, isLate, inRange,
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
  import FailureNotes from "../lib/FailureNotes.svelte";

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
  let expanded = $state<Record<string, boolean>>({}); // hypotheses opened to show their test and lessons

  // What to show: ongoing ones or all, under way in a date range — remembered in this browser.
  const VIEW_KEY = "failures.view";
  type Show = "ongoing" | "overdue" | "all";
  type View = { show: Show; from: string; to: string };
  function savedView(): View {
    try {
      const v = JSON.parse(localStorage.getItem(VIEW_KEY) ?? "{}");
      const show: Show = ["ongoing", "overdue", "all"].includes(v.show) ? v.show : "ongoing";
      return { show, from: typeof v.from === "string" ? v.from : "", to: typeof v.to === "string" ? v.to : "" };
    } catch {
      return { show: "ongoing", from: "", to: "" };
    }
  }
  const view = $state(savedView());
  $effect(() => {
    const v = JSON.stringify(view);
    try { localStorage.setItem(VIEW_KEY, v); } catch {}
  });
  const filtered = $derived(view.show !== "all" || !!view.from || !!view.to);
  const day = today();
  const kept = (f: Failure) =>
    (view.show === "all" || (view.show === "ongoing" ? !f.done_on : isLate(f, day))) && inRange(f, view.from, view.to);
  // the one you came to, or just saved, is shown whatever the view
  const shown = $derived(board?.items.filter((f) => f.id === target || kept(f)) ?? []);
  const overdue = $derived(board?.items.filter((f) => isLate(f, day)).length ?? 0);
  const notesOf = (f: Failure) => board?.notes.filter((n) => n.failure_id === f.id) ?? [];
  function noteCount(f: Failure): string {
    const ns = notesOf(f);
    const o = ns.filter((n) => n.kind === "observation").length;
    const c = ns.length - o;
    return [o && `${o} observation${o === 1 ? "" : "s"}`, c && `${c} calibration${c === 1 ? "" : "s"}`].filter(Boolean).join(", ");
  }

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
      expanded[f] = true; // the one you came for, in full
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
  async function setDone(f: Failure, done: boolean) {
    const done_on = done ? today() : null;
    if (board) board.items = board.items.map((x) => (x.id === f.id ? { ...x, done_on } : x)); // at once; it stays in view until reload
    target = f.id;
    try {
      await undoable(done ? "Completed hypothesis" : "Reopened hypothesis", () => saveFailure(f.id, { done_on }));
    } catch (e) {
      const m = (e as Error).message;
      await load(); // back as it was (this clears the message, so it is set after)
      error = m.includes("done_on") ? "Completing needs web/db/0054_failure_progress.sql run first." : m;
    }
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
    <div class="filters">
      <div class="pick" role="group" aria-label="Which hypotheses">
        <button class:on={view.show === "ongoing"} aria-pressed={view.show === "ongoing"} onclick={() => (view.show = "ongoing")}>Ongoing</button>
        <button class:on={view.show === "overdue"} aria-pressed={view.show === "overdue"} class:warn={overdue > 0}
                onclick={() => (view.show = "overdue")}>{overdue ? `⚠ Overdue (${overdue})` : "Overdue"}</button>
        <button class:on={view.show === "all"} aria-pressed={view.show === "all"} onclick={() => (view.show = "all")}>All</button>
      </div>
      <label>From <input type="date" bind:value={view.from} max={view.to || undefined} /></label>
      <label>To <input type="date" bind:value={view.to} min={view.from || undefined} /></label>
      {#if view.from || view.to}<button class="mini" onclick={() => { view.from = ""; view.to = ""; }}>Any dates</button>{/if}
      <span class="muted count">
        {shown.length} of {board.items.length} {board.items.length === 1 ? "hypothesis" : "hypotheses"}
        {#if view.from || view.to}· under way in these dates{/if}
      </span>
    </div>
    {#if editing?.kind === "theme" && editing.id === null}{@render themeForm(null, true)}{/if}
    {#if editing?.kind === "new" && editing.theme === null}{@render newForm(null, editing.attach)}{/if}

    {#each board.themes as t (t.id)}
      {@const every = board.items.filter((f) => f.theme_id === t.id)}
      {@const items = shown.filter((f) => f.theme_id === t.id)}
      <section class="theme">
        {#if editing?.kind === "theme" && editing.id === t.id}
          {@render themeForm(t, !every.length)}
        {:else}
          <header>
            <h2>{t.name}</h2>
            <span class="muted count">
              {#if filtered}{items.length} of {every.length} shown{:else}{every.length} {every.length === 1 ? "hypothesis" : "hypotheses"}{/if}
            </span>
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
            {@const late = isLate(f, today())}
            <!-- two lines each, so many fit in view; click the hypothesis for its test and lessons -->
            <article class="card" id={`fail-${f.id}`} class:target={target === f.id} class:done={!!f.done_on}>
              <div class="line1">
                <input type="checkbox" class="tick" checked={!!f.done_on} disabled={!!editing}
                       title={f.done_on ? "Completed — untick to reopen" : "Mark it complete"}
                       aria-label={`Completed: ${f.hypothesis}`} onchange={(e) => setDone(f, e.currentTarget.checked)} />
                <button class="hypothesis" aria-expanded={!!expanded[f.id]} title={f.hypothesis}
                        onclick={() => (expanded[f.id] = !expanded[f.id])}>
                  <span class="caret" aria-hidden="true">{expanded[f.id] ? "▾" : "▸"}</span>
                  <span class="text">{f.hypothesis}</span>
                </button>
                <span class="date">Created {fmtDay(f.created_on)}</span>
                <span class="date" class:overdue={late}>
                  {#if f.done_on}Completed {fmtDay(f.done_on)}
                  {:else if f.due_on}{late ? "⚠ " : ""}Deadline {fmtDay(f.due_on)}{late ? " · overdue" : ""}
                  {:else}No deadline{/if}
                </span>
                <button class="mini" onclick={() => (editing = { kind: "failure", id: f.id })} disabled={!!editing}>Edit</button>
              </div>
              <div class="line2">
                {#if where}<span class="where">{where}</span>
                {:else if isLinked(f)}<span class="where none">Its project was deleted</span>
                {:else}<span class="where none">No project</span>{/if}
                {#if notesOf(f).length}
                  <button class="notes-count" onclick={() => (expanded[f.id] = true)}>{noteCount(f)}</button>
                {/if}
                {#if at.project}
                  <button class="mini" onclick={() => go(f, planningHash(at.project!.id, at.milestone?.id, f.id))}
                          disabled={!!editing}>Open in Planning ›</button>
                {/if}
                {#if at.group && member}
                  <button class="mini" onclick={() => go(f, membersHash(member, at.group!.id, at.groupMilestone?.id, f.id))}
                          disabled={!!editing}>Open in Members ›</button>
                {/if}
              </div>
              {#if expanded[f.id]}
                <dl>
                  <dt>Hypothesis</dt>
                  <dd><Linked text={f.hypothesis} /></dd>
                  <dt>Test</dt>
                  <dd class:blank={!f.test}>{#if f.test}<Linked text={f.test} />{:else}Not written yet{/if}</dd>
                  <dt>Lessons from failure</dt>
                  <dd class:blank={!f.lesson}>{#if f.lesson}<Linked text={f.lesson} />{:else}Not written yet{/if}</dd>
                </dl>
                <FailureNotes failureId={f.id} notes={notesOf(f)} disabled={!!editing} onchanged={load} />
              {/if}
            </article>
          {/if}
        {:else}
          <p class="muted empty">
            {#if every.length}None {view.show !== "all" && !view.from && !view.to ? view.show : "in this view"}.{:else}No hypotheses yet.{/if}
          </p>
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
  .bar, header, .theme-form { display: flex; flex-wrap: wrap; gap: 0.4rem 0.6rem; font-family: var(--font-ui); }
  .bar { margin-bottom: 0.8rem; }
  .filters { display: flex; flex-wrap: wrap; gap: 0.5rem 0.9rem; align-items: center; font-family: var(--font-ui); font-size: 0.82rem; }
  .filters label { display: flex; align-items: center; gap: 0.35rem; color: var(--ink-soft); }
  .filters input { width: auto; padding: 0.2rem 0.4rem; font-size: 0.82rem; }
  .pick { display: flex; gap: 0.25rem; }
  .pick button { font-size: 0.8rem; padding: 0.2rem 0.7rem; }
  .pick button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .pick button.warn:not(.on) { color: var(--danger); border-color: var(--danger); }
  .notes-count { border: none; background: none; padding: 0; font-size: 0.75rem; color: var(--ink-soft); text-decoration: underline dotted; }
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
    padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--rule); font-family: var(--font-ui);
    scroll-margin-top: 4.5rem;
  }
  .card:hover { background: var(--panel); }
  .card.target { animation: lit 3s ease-out; }
  @keyframes lit { from, 40% { background: color-mix(in srgb, var(--accent) 22%, transparent); } to { background: transparent; } }
  /* the same columns on every line, so dates line up down the list */
  .line1 { display: grid; grid-template-columns: auto minmax(0, 1fr) 8.5rem 13.5rem auto; gap: 0.2rem 0.8rem; align-items: baseline; }
  .line2 { display: flex; flex-wrap: wrap; gap: 0.2rem 0.5rem; padding-left: 2.9rem; font-size: 0.78rem; }
  .tick { width: auto; margin: 0; align-self: center; accent-color: var(--accent); cursor: pointer; }
  .card.done .hypothesis .text { text-decoration: line-through; color: var(--ink-soft); font-weight: 500; }
  .hypothesis {
    display: flex; gap: 0.3rem; align-items: baseline; min-width: 0; padding: 0; border: none; background: none;
    text-align: left; font-size: 0.92rem; font-weight: 600; color: var(--ink);
  }
  .hypothesis .text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .caret { flex: none; width: 0.9rem; font-size: 0.7rem; color: var(--ink-soft); }
  .date { font-size: 0.78rem; color: var(--ink-soft); white-space: nowrap; font-variant-numeric: tabular-nums; }
  .where { flex: 1; min-width: 0; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .where.none { color: var(--ink-soft); }
  dl {
    display: grid; grid-template-columns: 10rem minmax(0, 1fr); gap: 0.3rem 0.8rem; margin: 0.4rem 0 0.2rem 2.9rem;
    font-size: 0.86rem;
  }
  dt { color: var(--ink-soft); }
  dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  dd.blank { color: var(--ink-soft); font-style: italic; }
  .overdue { color: var(--danger); }
  .mini { font-size: 0.75rem; padding: 0.1rem 0.5rem; white-space: nowrap; }
  @media (max-width: 40rem) {
    .line1 { display: flex; flex-wrap: wrap; gap: 0.1rem 0.7rem; }
    .line1 .hypothesis { flex: 1 0 calc(100% - 2rem); }
    .line1 .date:first-of-type { padding-left: 2.9rem; }
    .line1 .mini { margin-left: auto; }
    .line2 .where { flex-basis: 100%; }
    dl { grid-template-columns: minmax(0, 1fr); margin-left: 0; }
  }
</style>
