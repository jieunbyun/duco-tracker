<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = { skill: null as string | null, opened: {} as Record<string, boolean>, showDone: false, formOpen: null as string | null };
</script>

<script lang="ts">
  // Practice: goals practised over days, and under each the day's sessions of reading,
  // writing or speaking, each with your own evaluation.
  import {
    loadBook, savePractice, deletePractice, saveSession, deleteSession, SKILLS, CRITERIA, skillLabel, average, formulationSize,
  } from "../lib/practice";
  import type { Book, Practice, Session, Skill, Formulation } from "../lib/practice";
  import { undoable } from "../lib/undo.svelte";
  import { fmtDay, today } from "../lib/dates";
  import { arrivedAt } from "../lib/dayBack.svelte";
  import { tick } from "svelte";
  import PracticeSession from "../lib/PracticeSession.svelte";
  import FormulationEditor from "../lib/FormulationEditor.svelte";

  let book = $state<Book | null>(null);
  let missing = $state(false);
  let loading = $state(true);
  let error = $state("");
  let skill = $state<Skill | null>(last.skill as Skill | null); // show only this skill's sessions
  let opened = $state<Record<string, boolean>>(last.opened); // sessions opened to read their feedback
  let showDone = $state(last.showDone);
  // what is being edited: a practice ("new" for a new one), or a session (under a practice)
  let editing = $state<string | null>(null);
  let draft = $state({ title: "", goal: "" });
  let sessionForm = $state<{ practice: string; session: Session | null } | null>(null);
  let formOpen = $state<string | null>(last.formOpen); // the practice whose problem formulation is open

  $effect(() => {
    Object.assign(last, { skill, opened, showDone, formOpen });
  });

  async function load() {
    try {
      const b = await loadBook();
      missing = b === null;
      book = b;
      arrive();
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  // from the Day tab (#/practice?s=<session>): that session open to change
  const arrived = arrivedAt("practice");
  async function arrive() {
    const id = arrived.get("s");
    arrived.delete("s");
    const s = book?.sessions.find((x) => x.id === id);
    if (!s) return;
    skill = null;
    if (practices.find((p) => p.id === s.practice_id)?.done_on) showDone = true;
    editing = null;
    sessionForm = { practice: s.practice_id, session: s };
    await tick();
    document.querySelector(".sessions li.editing")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  const practices = $derived(book?.practices ?? []);
  const active = $derived(practices.filter((p) => !p.done_on));
  const finished = $derived(practices.filter((p) => p.done_on));
  const sessionsOf = (id: string) => (book?.sessions ?? []).filter((s) => s.practice_id === id);
  const shown = (id: string) => sessionsOf(id).filter((s) => !skill || s.skill === skill);
  const lastFocus = (id: string) => sessionsOf(id).find((s) => s.next_focus)?.next_focus ?? null;

  async function act(label: string, run: () => Promise<unknown>) {
    try {
      await undoable(label, run);
      await load();
      return true;
    } catch (e) {
      const m = (e as Error).message;
      error = /formulation|skill_check/.test(m)
        ? "Problem formulation needs web/db/0057_practice_formulation.sql run first, in the Supabase SQL editor."
        : `Not saved: ${m}`;
      return false;
    }
  }
  function saveFormulation(p: Practice, f: Formulation) {
    return act("Saved problem formulation", () => savePractice(p.id, { formulation: f }));
  }

  function startEdit(p: Practice | null) {
    sessionForm = null;
    editing = p?.id ?? "new";
    draft = { title: p?.title ?? "", goal: p?.goal ?? "" };
  }
  async function saveDraft(ev: SubmitEvent) {
    ev.preventDefault();
    const title = draft.title.trim();
    if (!title) return;
    const id = editing === "new" ? null : editing;
    if (await act(id ? "Changed practice" : "Added practice", () => savePractice(id, { title, goal: draft.goal.trim() || null })))
      editing = null;
  }
  function finish(p: Practice) {
    act(p.done_on ? "Reopened practice" : "Finished practice", () => savePractice(p.id, { done_on: p.done_on ? null : today() }));
  }
  function remove(p: Practice) {
    const n = sessionsOf(p.id).length;
    const parts = [n ? `its ${n} ${n === 1 ? "session" : "sessions"}` : "", p.formulation ? "its problem formulation" : ""].filter(Boolean);
    if (!confirm(`Delete “${p.title}”${parts.length ? ` and ${parts.join(" and ")}` : ""}?`)) return;
    act("Deleted practice", () => deletePractice(p.id));
  }

  function newSession(p: Practice) {
    editing = null;
    sessionForm = { practice: p.id, session: null };
  }
  async function storeSession(fields: Parameters<typeof saveSession>[1]) {
    const f = sessionForm!;
    if (await act(f.session ? "Changed session" : "Added session", () => saveSession(f.session?.id ?? null, { ...fields, practice_id: f.practice })))
      sessionForm = null;
  }
  function removeSession(s: Session) {
    if (!confirm(`Delete the ${skillLabel(s.skill).toLowerCase()} session of ${fmtDay(s.done_on)}?`)) return;
    act("Deleted session", () => deleteSession(s.id));
  }

  const avg = (s: Session) => average(s.ratings);
  const count = (id: string, k: Skill) => sessionsOf(id).filter((s) => s.skill === k).length;
</script>

<section class="practice">
  <div class="head">
    <div>
      <span class="eyebrow">Practice</span>
      <h1>Reading, writing &amp; speaking</h1>
    </div>
    {#if !missing}<button class="primary" onclick={() => startEdit(null)}>+ New practice</button>{/if}
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if missing}
    <p class="muted">Practice needs its tables first: run <code>web/db/0055_practice.sql</code> in the Supabase SQL editor, then reload.</p>
  {:else}
    <div class="filter" role="group" aria-label="Skill">
      <button class="chip" class:on={skill === null} onclick={() => (skill = null)}>All skills</button>
      {#each SKILLS as k (k.key)}
        <button class="chip" class:on={skill === k.key} onclick={() => (skill = skill === k.key ? null : k.key)}>{k.label}</button>
      {/each}
    </div>

    {#if editing === "new"}{@render form()}{/if}

    {#if !practices.length && editing !== "new"}
      <p class="muted">Nothing yet. Start a practice with a goal — “Present paper X in 10 minutes”, “Draft the
        introduction”, “Read and critique three papers on Y” — then add a session for each day you work on it.</p>
    {/if}

    {#each active as p (p.id)}{@render card(p)}{/each}

    {#if finished.length}
      <button class="more" onclick={() => (showDone = !showDone)}>{showDone ? "▾" : "▸"} Finished ({finished.length})</button>
      {#if showDone}{#each finished as p (p.id)}{@render card(p)}{/each}{/if}
    {/if}
  {/if}
</section>

{#snippet form()}
  <form class="practice-form" onsubmit={saveDraft}>
    <label>Practice <input bind:value={draft.title} required placeholder="e.g. Conference talk on paper X" /></label>
    <label>Goal <textarea rows="2" bind:value={draft.goal} placeholder="What done well looks like: a 10-minute talk, clear in one run-through, ready for questions"></textarea></label>
    <div class="buttons">
      <button class="primary" type="submit">{editing === "new" ? "Add practice" : "Save"}</button>
      <button type="button" onclick={() => (editing = null)}>Cancel</button>
    </div>
  </form>
{/snippet}

{#snippet card(p: Practice)}
  {@const list = shown(p.id)}
  {@const focus = lastFocus(p.id)}
  <article class="card" class:done={p.done_on}>
    {#if editing === p.id}
      {@render form()}
    {:else}
      <div class="top">
        <h2>{p.title}</h2>
        <span class="muted dates">{p.done_on ? `${fmtDay(p.started_on)} – ${fmtDay(p.done_on)}` : `Since ${fmtDay(p.started_on)}`}</span>
        <span class="tools">
          {#if !p.done_on}<button class="primary" onclick={() => newSession(p)}>+ Session</button>{/if}
          <button onclick={() => finish(p)}>{p.done_on ? "Reopen" : "Finish"}</button>
          <button onclick={() => startEdit(p)}>Edit</button>
          <button class="del" onclick={() => remove(p)} aria-label="Delete practice">Delete</button>
        </span>
      </div>
      {#if p.goal}<p class="goal"><span class="eyebrow">Goal</span>{p.goal}</p>{/if}
      <p class="counts muted">
        {#each SKILLS as k, i (k.key)}{i ? " · " : ""}{k.label} {count(p.id, k.key)}{/each}
      </p>
      {#if focus && !p.done_on && sessionForm?.practice !== p.id}
        <p class="focus"><span class="eyebrow">Focus next time</span>{focus}</p>
      {/if}
    {/if}

    {#if formOpen === p.id}
      <FormulationEditor formulation={p.formulation ?? null} onsave={(f) => saveFormulation(p, f)} onclose={() => (formOpen = null)} />
    {:else if p.formulation}
      {@const n = formulationSize(p.formulation)}
      <button class="formulation-line" onclick={() => (formOpen = p.id)}>
        <span class="eyebrow">Problem formulation ›</span>
        <span class="q">{p.formulation.question.trim() || "The debate, not yet written"}</span>
        <span class="muted small">{n.views} {n.views === 1 ? "view" : "views"} · {n.objectives} objectives{n.byTag.length ? ` (${n.byTag.map((t) => `${t.n} ${t.label.toLowerCase()}`).join(", ")})` : ""} · {n.assumptions} assumptions ·
          {n.conflicts} {n.conflicts === 1 ? "conflict" : "conflicts"} · {n.data} {n.data === 1 ? "dataset" : "datasets"}</span>
      </button>
    {:else}
      <button class="add-formulation" onclick={() => (formOpen = p.id)}>+ Problem formulation</button>
    {/if}

    {#if sessionForm?.practice === p.id && !sessionForm.session}
      <PracticeSession skill={skill ?? "reading"} {focus} onsave={storeSession} oncancel={() => (sessionForm = null)} />
    {/if}

    {#if list.length}
      <ul class="sessions">
        {#each list as s (s.id)}
          {@const a = avg(s)}
          <li class:editing={sessionForm?.session?.id === s.id}>
            {#if sessionForm?.session?.id === s.id}
              <PracticeSession session={s} onsave={storeSession} oncancel={() => (sessionForm = null)} />
            {:else}
              <button class="line" aria-expanded={!!opened[s.id]} onclick={() => (opened = { ...opened, [s.id]: !opened[s.id] })}>
                <span class="date">{fmtDay(s.done_on)}</span>
                <span class="skill {s.skill}">{skillLabel(s.skill)}</span>
                <span class="what">{s.did ?? ""}</span>
                <span class="nums muted">{s.minutes != null ? `${s.minutes} min` : ""}{a != null ? `${s.minutes != null ? " · " : ""}${a.toFixed(1)}/5` : ""}</span>
              </button>
              {#if opened[s.id]}
                <div class="feedback">
                  {#if s.did}<p><span class="eyebrow">What you did</span>{s.did}</p>{/if}
                  {#if Object.keys(s.ratings).length}
                    <ul class="scores">
                      {#each CRITERIA[s.skill].filter((c) => s.ratings[c]) as c (c)}<li>{c} <strong>{s.ratings[c]}</strong></li>{/each}
                    </ul>
                  {/if}
                  {#if s.went_well}<p><span class="eyebrow">Went well</span>{s.went_well}</p>{/if}
                  {#if s.to_fix}<p><span class="eyebrow">To fix</span>{s.to_fix}</p>{/if}
                  {#if s.next_focus}<p><span class="eyebrow">Focus next time</span>{s.next_focus}</p>{/if}
                  <div class="buttons">
                    <button onclick={() => { editing = null; sessionForm = { practice: p.id, session: s }; }}>Edit</button>
                    <button class="del" onclick={() => removeSession(s)}>Delete</button>
                  </div>
                </div>
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
    {:else if skill && sessionsOf(p.id).length}
      <p class="muted none">No {skillLabel(skill).toLowerCase()} sessions here.</p>
    {/if}
  </article>
{/snippet}

<style>
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
  .head h1 { margin: 0; }
  .filter { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 1rem; font-family: var(--font-ui); }
  .chip { font-size: 0.82rem; padding: 0.2rem 0.75rem; border-radius: 999px; background: none; }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .card { border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.9rem 1rem; margin-bottom: 1rem; display: grid; gap: 0.6rem; background: var(--paper); }
  .card.done { opacity: 0.85; }
  .top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.3rem 0.8rem; }
  .top h2 { margin: 0; font-size: 1.15rem; }
  .dates { font-family: var(--font-ui); font-size: 0.82rem; }
  .tools { margin-left: auto; display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .tools button, .buttons button { font-size: 0.82rem; padding: 0.3rem 0.7rem; }
  .del { color: var(--danger); }
  .goal, .focus, .feedback p { margin: 0; white-space: pre-wrap; }
  .eyebrow { display: block; }
  .focus { padding: 0.5rem 0.7rem; border-left: 3px solid var(--accent); background: var(--panel); border-radius: var(--radius); }
  .counts { margin: 0; font-family: var(--font-ui); font-size: 0.8rem; }
  .sessions { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule); }
  .sessions > li { border-bottom: 1px solid var(--rule); }
  .sessions > li.editing { padding: 0.5rem 0; border-bottom: none; }
  .line {
    width: 100%; display: grid; grid-template-columns: 7.5rem 6.5rem minmax(0, 1fr) auto; gap: 0.6rem; align-items: baseline;
    text-align: left; background: none; border: none; border-radius: 0; padding: 0.45rem 0.2rem; font-size: 0.9rem;
  }
  .line:hover { background: var(--panel); }
  .date { font-family: var(--font-ui); font-size: 0.82rem; font-variant-numeric: tabular-nums; }
  .skill { font-family: var(--font-ui); font-size: 0.75rem; border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.5rem; justify-self: start; }
  .skill.reading { border-color: var(--series-1); }
  .skill.writing { border-color: var(--series-2); }
  .skill.speaking { border-color: var(--series-3); }
  .skill.formulation { border-color: var(--series-4); }
  .formulation-line { display: grid; gap: 0.15rem; text-align: left; background: var(--panel); border: 1px solid var(--rule); padding: 0.5rem 0.7rem; }
  .formulation-line:hover { border-color: var(--accent); }
  .formulation-line .q { white-space: pre-wrap; }
  .formulation-line .small { font-family: var(--font-ui); font-size: 0.78rem; }
  .add-formulation { justify-self: start; font-size: 0.82rem; padding: 0.25rem 0.7rem; background: none; border-style: dashed; color: var(--ink-soft); }
  .what { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .nums { font-family: var(--font-ui); font-size: 0.8rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .feedback { display: grid; gap: 0.5rem; padding: 0.3rem 0.2rem 0.8rem; }
  .scores { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; font-family: var(--font-ui); font-size: 0.85rem; }
  .buttons { display: flex; gap: 0.5rem; }
  .none { margin: 0; font-size: 0.85rem; }
  .more { background: none; border: none; padding: 0.3rem 0; font-family: var(--font-ui); color: var(--ink-soft); margin-bottom: 0.6rem; }
  .practice-form { display: grid; gap: 0.6rem; padding: 0.9rem; border: 1px solid var(--rule); border-radius: var(--radius); margin-bottom: 1rem; }
  .card .practice-form { margin: 0; border: none; padding: 0; }
  .practice-form label { display: grid; gap: 0.25rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  @media (max-width: 40rem) {
    .line { grid-template-columns: auto auto minmax(0, 1fr); }
    .what { grid-column: 1 / -1; grid-row: 2; }
    .tools { margin-left: 0; }
  }
</style>
