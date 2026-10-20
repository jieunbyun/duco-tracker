<script lang="ts">
  import {
    FIELDS, saveEntry, deleteEntry, deletable, loadRevisions, addComment, deleteComment, parseLinks, linkName,
  } from "./group";
  import type { Entry, EntryKind, GroupProject, GroupMilestone, Member, Comment, Revision, PlanningRef } from "./group";
  import { planningGroups } from "./group";
  import { saveEntry as saveTimeEntry } from "./data";
  import { stepSummary } from "./actions";
  import type { ActionStep } from "./actions";
  import ActionsInline from "./ActionsInline.svelte";
  import { today, fmtDay } from "./dates";

  type Props = {
    entries: Entry[];
    projects: GroupProject[]; // the shared projects these entries can be about
    planning?: PlanningRef[]; // and your own Planning projects (yours only), with their milestones
    groupMilestones?: GroupMilestone[]; // the shared projects' milestones
    members: Member[];
    comments: Comment[];
    edits: Map<string, number>; // how often each entry was edited
    me: string;
    canWrite: boolean; // the author's own logbook
    onchanged: () => Promise<void>;
  };
  let { entries, projects, planning = [], groupMilestones = [], members, comments, edits, me, canWrite, onchanged }: Props = $props();

  const nameOf = (id: string) => members.find((m) => m.user_id === id)?.display_name ?? "—";
  const projectOf = (e: Entry) => e.planning_project_id ? planning.find((p) => p.id === e.planning_project_id)?.name ?? "(project removed)"
    : e.project_id ? projects.find((p) => p.id === e.project_id)?.title ?? "(project removed)" : "No project";
  const milestoneOf = (e: Entry) => e.planning_milestone_id
    ? planning.flatMap((p) => p.milestones).find((m) => m.id === e.planning_milestone_id)?.title
    : e.group_milestone_id ? groupMilestones.find((m) => m.id === e.group_milestone_id)?.title : undefined;
  /** The chosen project's milestones: its active ones (and the one already chosen), or all when asked. */
  let allMilestones = $state(false);
  const milestonesOf = (pick: string): { id: string; title: string; active?: boolean }[] =>
    pick.startsWith("p:") ? planning.find((p) => p.id === pick.slice(2))?.milestones ?? []
    : pick.startsWith("g:") ? groupMilestones.filter((m) => m.project_id === pick.slice(2)).map((m) => ({ id: m.id, title: m.title, active: !m.done }))
    : [];
  const milestonesFor = (pick: string, chosen: string) =>
    milestonesOf(pick).filter((m) => allMilestones || m.active !== false || m.id === chosen);
  // the Project menu holds both kinds: "g:<id>" a shared project, "p:<id>" a Planning one
  const pick = (e: Pick<Entry, "project_id" | "planning_project_id">) =>
    e.planning_project_id ? `p:${e.planning_project_id}` : e.project_id ? `g:${e.project_id}` : "";
  let error = $state("");

  // ---- writing (a new entry, or editing one) ---------------------------------------
  type Time = { mode: "none" | "times" | "minutes"; start: string; end: string; minutes: number | null; core: boolean };
  type Draft = {
    id: string | null; kind: EntryKind; entry_date: string; project_id: string; milestone: string;
    did: string; results: string; next: string; links: string;
    log: ActionStep[]; // what this session did to action items
    time: Time; // the block's time, logged once (Planning projects)
  };
  const noTime = (): Time => ({ mode: "none", start: "09:00", end: "10:00", minutes: 60, core: false });
  const blank = (): Draft => ({
    id: null, kind: "entry", entry_date: today(),
    project_id: (() => { const g = projects.find((p) => p.status === "active"); return g ? `g:${g.id}` : ""; })(), milestone: "",
    did: "", results: "", next: "", links: "", log: [], time: noTime(),
  });
  let draft = $state<Draft>(blank());
  let editing = $state<string | null>(null); // id of the entry being edited in place
  const editingEntry = $derived(entries.find((x) => x.id === editing) ?? null);
  let busy = $state(false);

  function startEdit(e: Entry) {
    editing = e.id;
    draft = { id: e.id, kind: e.kind, entry_date: e.entry_date, project_id: pick(e),
              milestone: e.planning_milestone_id ?? e.group_milestone_id ?? "", did: e.did ?? "",
              results: e.results ?? "", next: e.next ?? "", links: e.links.join("\n"),
              log: [...(e.actions ?? [])], time: noTime() };
  }
  async function save(ev: SubmitEvent) {
    ev.preventDefault();
    if (!draft.did.trim() && !draft.results.trim() && !draft.next.trim()) return (error = "Write something first.");
    busy = true;
    error = "";
    try {
      // the session's time, once, on the project (and milestone) — never per action
      let timeFields = {};
      const t = draft.time;
      if (t.mode !== "none" && draft.project_id.startsWith("p:")) {
        const pp = planning.find((p) => p.id === draft.project_id.slice(2));
        if (!pp?.category_id) throw new Error("That project has no category to log time under.");
        const day = draft.entry_date || today();
        const started_at = `${day}T${t.start}:00+00:00`;
        let ended_at: string | null = null, mins: number;
        if (t.mode === "times") {
          ended_at = t.end === "00:00" ? `${new Date(Date.parse(day) + 86_400_000).toISOString().slice(0, 10)}T00:00:00+00:00` : `${day}T${t.end}:00+00:00`;
          mins = (Date.parse(ended_at) - Date.parse(started_at)) / 60_000;
          if (mins <= 0) throw new Error("The session must end after it starts.");
        } else {
          mins = Math.round(t.minutes ?? 0);
          if (mins <= 0) throw new Error("Give the minutes.");
        }
        const time_entry_id = await saveTimeEntry(null, {
          category_id: pp.category_id, project_id: pp.id, milestone_id: draft.milestone || null,
          started_at, ended_at, manual_minutes: t.mode === "minutes" ? mins : null,
          description: (draft.did.trim().split("\n")[0] || "Logbook session").slice(0, 120), is_core: t.core,
        });
        timeFields = { time_entry_id, time_minutes: mins };
      }
      await saveEntry(draft.id, {
        ...timeFields,
        actions: draft.log,
        kind: draft.kind, entry_date: draft.entry_date || today(),
        project_id: draft.project_id.startsWith("g:") ? draft.project_id.slice(2) : null,
        planning_project_id: draft.project_id.startsWith("p:") ? draft.project_id.slice(2) : null,
        planning_milestone_id: draft.project_id.startsWith("p:") ? draft.milestone || null : null,
        group_milestone_id: draft.project_id.startsWith("g:") ? draft.milestone || null : null,
        did: draft.did.trim() || null, results: draft.results.trim() || null, next: draft.next.trim() || null,
        links: parseLinks(draft.links),
      });
      const kind = draft.kind, project = draft.project_id, milestone = draft.milestone; // ready for the next session
      draft = { ...blank(), kind, project_id: project, milestone };
      editing = null;
      await onchanged();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
  function cancelEdit() {
    editing = null;
    draft = blank();
  }
  async function remove(e: Entry) {
    if (!confirm("Delete this entry? (Possible only on the day it was written.)")) return;
    try { await deleteEntry(e.id); await onchanged(); } catch (err) { error = (err as Error).message; }
  }

  // ---- history ---------------------------------------------------------------------
  let history = $state<Record<string, Revision[] | "loading">>({});
  async function toggleHistory(e: Entry) {
    if (history[e.id]) return void delete history[e.id];
    history[e.id] = "loading";
    try { history[e.id] = await loadRevisions(e.id); } catch (err) { error = (err as Error).message; delete history[e.id]; }
  }

  // ---- comments --------------------------------------------------------------------
  let reply = $state<Record<string, string>>({});
  async function comment(e: Entry) {
    const body = (reply[e.id] ?? "").trim();
    if (!body) return;
    try { await addComment(e.id, body); reply[e.id] = ""; await onchanged(); } catch (err) { error = (err as Error).message; }
  }
  async function uncomment(c: Comment) {
    if (!confirm("Delete this comment?")) return;
    try { await deleteComment(c.id); await onchanged(); } catch (err) { error = (err as Error).message; }
  }
</script>

{#snippet form(isEdit: boolean)}
  <form class="lb-form" class:inline={isEdit} onsubmit={save}>
    <div class="lb-row">
      <div class="seg" role="group" aria-label="Kind of entry">
        <button type="button" class:on={draft.kind === "entry"} aria-pressed={draft.kind === "entry"} onclick={() => (draft.kind = "entry")}>Entry</button>
        <button type="button" class:on={draft.kind === "weekly"} aria-pressed={draft.kind === "weekly"} onclick={() => (draft.kind = "weekly")}>Weekly update</button>
      </div>
      <label class="small">Date <input type="date" bind:value={draft.entry_date} /></label>
      <label class="small grow">Project
        <select bind:value={draft.project_id} onchange={() => (draft.milestone = "")}>
          <option value="">No project</option>
          {#if planning.length}
            {#if projects.length}
              <optgroup label="Shared projects">{#each projects as p (p.id)}<option value={`g:${p.id}`}>{p.title}</option>{/each}</optgroup>
            {/if}
            {#each planningGroups(planning) as g (g.label)}
              <optgroup label={g.label}>{#each g.items as p (p.id)}<option value={`p:${p.id}`}>{p.name}</option>{/each}</optgroup>
            {/each}
          {:else}
            {#each projects as p (p.id)}<option value={`g:${p.id}`}>{p.title}</option>{/each}
          {/if}
        </select>
      </label>
      {#if milestonesOf(draft.project_id).length}
        <label class="small grow">Milestone
          <select bind:value={draft.milestone}>
            <option value="">—</option>
            {#each milestonesFor(draft.project_id, draft.milestone) as m (m.id)}<option value={m.id}>{m.title}{m.active === false ? " (not active)" : ""}</option>{/each}
          </select>
        </label>
        {#if milestonesOf(draft.project_id).some((m) => m.active === false)}
          <label class="small check"><input type="checkbox" bind:checked={allMilestones} /> show all milestones</label>
        {/if}
      {/if}
    </div>
    {#if draft.project_id}
      {#key draft.project_id}
        <ActionsInline projectKey={draft.project_id} milestoneId={draft.project_id.startsWith("p:") ? draft.milestone : ""}
                       log={draft.log} onlog={(l) => (draft.log = l)} />
      {/key}
    {/if}
    <label>{FIELDS[draft.kind].did} <textarea rows="3" bind:value={draft.did}></textarea></label>
    <label>{FIELDS[draft.kind].results} <textarea rows="2" bind:value={draft.results}></textarea></label>
    <label>{FIELDS[draft.kind].next} <textarea rows="2" bind:value={draft.next}></textarea></label>
    <label>Links — files and folders on OneDrive, one per line
      <textarea rows="2" bind:value={draft.links} placeholder="https://…sharepoint.com/…"></textarea>
    </label>
    {#if draft.project_id.startsWith("p:") && !(isEdit && editingEntry?.time_entry_id)}
      <div class="lb-time">
        <span class="small">Time spent</span>
        <div class="seg" role="group" aria-label="Time spent">
          <button type="button" class:on={draft.time.mode === "none"} onclick={() => (draft.time.mode = "none")}>not logged</button>
          <button type="button" class:on={draft.time.mode === "times"} onclick={() => (draft.time.mode = "times")}>start & end</button>
          <button type="button" class:on={draft.time.mode === "minutes"} onclick={() => (draft.time.mode = "minutes")}>minutes</button>
        </div>
        {#if draft.time.mode !== "none"}
          <input type="time" bind:value={draft.time.start} step="300" aria-label="Start" />
          {#if draft.time.mode === "times"}–<input type="time" bind:value={draft.time.end} step="300" aria-label="End" />
          {:else}<input type="number" min="5" step="5" bind:value={draft.time.minutes} aria-label="Minutes" /> min{/if}
          <label class="small check"><input type="checkbox" bind:checked={draft.time.core} /> core</label>
          <span class="muted small">logged once, on this project{draft.milestone ? " and milestone" : ""}, as in Week</span>
        {/if}
      </div>
    {/if}
    <div class="lb-actions">
      <button class="primary" type="submit" disabled={busy}>{busy ? "Saving…" : isEdit ? "Save changes" : "Add to logbook"}</button>
      {#if isEdit}<button type="button" onclick={cancelEdit}>Cancel</button>
        <span class="muted small">The version before this edit is kept in the entry's history.</span>{/if}
    </div>
  </form>
{/snippet}

{#if error}<p class="error">{error}</p>{/if}
{#if canWrite && !editing}{@render form(false)}{/if}

{#each entries as e (e.id)}
  {@const f = FIELDS[e.kind]}
  {@const cs = comments.filter((c) => c.entry_id === e.id)}
  <article class="entry" class:weekly={e.kind === "weekly"}>
    {#if editing === e.id}
      {@render form(true)}
    {:else}
      <header>
        <strong>{fmtDay(e.entry_date)}</strong>
        <span class="muted">· {projectOf(e)}{milestoneOf(e) ? ` › ${milestoneOf(e)}` : ""}</span>
        {#if e.kind === "weekly"}<span class="badge">weekly update</span>{/if}
        {#if e.author_id !== me}<span class="muted">· {nameOf(e.author_id)}</span>{/if}
        {#if edits.get(e.id)}
          <button class="link" onclick={() => toggleHistory(e)}>edited {edits.get(e.id)}× · {history[e.id] ? "hide history" : "history"}</button>
        {/if}
        {#if canWrite && e.author_id === me}
          <span class="spacer"></span>
          <button class="mini" onclick={() => startEdit(e)}>Edit</button>
          {#if deletable(e)}<button class="mini danger" onclick={() => remove(e)}>Delete</button>{/if}
        {/if}
      </header>
      {#if e.time_minutes || e.actions?.length}
        <p class="session muted small">
          {#if e.time_minutes}⏱ {Math.round((e.time_minutes / 60) * 100) / 100} h{e.actions?.length ? " · " : ""}{/if}{e.actions?.length ? stepSummary(e.actions) : ""}
        </p>
      {/if}
      {#each ["did", "results", "next"] as const as k (k)}
        {#if e[k]}<div class="field"><span class="label">{f[k]}</span><p>{e[k]}</p></div>{/if}
      {/each}
      {#if e.links.length}
        <div class="links">
          {#each e.links as l (l)}<a href={l} target="_blank" rel="noopener noreferrer" title={l}>↗ {linkName(l)}</a>{/each}
        </div>
      {/if}
      {#if history[e.id]}
        <div class="history">
          {#if history[e.id] === "loading"}<p class="muted small">Loading…</p>
          {:else}
            {#each history[e.id] as Revision[] as r (r.id)}
              {@const o = r.old_row}
              <div class="rev">
                <span class="muted small">Until {fmtDay(r.changed_at.slice(0, 10))} {r.changed_at.slice(11, 16)}:</span>
                {#each ["did", "results", "next"] as const as k (k)}
                  {#if o[k]}<div class="field"><span class="label">{FIELDS[o.kind ?? "entry"][k]}</span><p>{o[k]}</p></div>{/if}
                {/each}
                {#if o.links?.length}<p class="small muted">Links: {o.links.map(linkName).join(", ")}</p>{/if}
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    {/if}

    <div class="comments">
      {#each cs as c (c.id)}
        <div class="comment">
          <span class="who">{nameOf(c.author_id)}</span> <span class="muted small">{fmtDay(c.created_at.slice(0, 10))}</span>
          {#if c.author_id === me}<button class="x" aria-label="Delete comment" onclick={() => uncomment(c)}>✕</button>{/if}
          <p>{c.body}</p>
        </div>
      {/each}
      <form class="reply" onsubmit={(ev) => { ev.preventDefault(); comment(e); }}>
        <input bind:value={reply[e.id]} placeholder={e.author_id === me ? "Reply…" : "Comment…"} aria-label="Comment" />
        <button class="mini" type="submit" disabled={!(reply[e.id] ?? "").trim()}>Send</button>
      </form>
    </div>
  </article>
{:else}
  <p class="muted">No entries yet.</p>
{/each}

<style>
  .lb-form { display: grid; gap: 0.6rem; padding: 0.8rem; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--panel); margin-bottom: 1rem; font-family: var(--font-ui); }
  .lb-form.inline { margin: 0; }
  .lb-form label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .lb-row { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: end; }
  .lb-row label.small { display: grid; }
  .lb-row input, .lb-row select { width: auto; }
  .grow { flex: 1; min-width: 12rem; }
  .grow select { width: 100%; }
  .lb-row .check { display: inline-flex; gap: 0.3rem; align-items: center; align-self: center; }
  .lb-row .check input { width: auto; }
  .seg { display: inline-flex; }
  .seg button { font-size: 0.82rem; padding: 0.35rem 0.7rem; border-radius: 0; }
  .seg button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
  .seg button:last-child { border-radius: 0 var(--radius) var(--radius) 0; margin-left: -1px; }
  .seg button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .lb-time { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
  .lb-time input[type="time"], .lb-time input[type="number"] { width: auto; font-size: 0.85rem; padding: 0.2rem 0.4rem; }
  .lb-time input[type="number"] { width: 5rem; }
  .lb-time .seg button { font-size: 0.78rem; padding: 0.25rem 0.55rem; }
  .session { margin: 0 0 0.3rem; }
  .lb-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }

  .entry { border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.7rem 0.9rem; margin-bottom: 0.8rem; background: var(--paper); }
  .entry.weekly { border-left: 4px solid var(--accent); }
  .entry header { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: baseline; font-family: var(--font-ui); font-size: 0.88rem; margin-bottom: 0.4rem; }
  .spacer { flex: 1; }
  .badge { font-size: 0.7rem; padding: 0.05rem 0.45rem; border-radius: 999px; background: var(--accent); color: var(--accent-ink); }
  .field { margin: 0.3rem 0; }
  .field .label { font-family: var(--font-ui); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-soft); }
  .field p { margin: 0.1rem 0 0; white-space: pre-wrap; }
  .links { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0; font-family: var(--font-ui); font-size: 0.82rem; }
  .links a { padding: 0.1rem 0.5rem; border: 1px solid var(--rule); border-radius: 999px; text-decoration: none; }
  .history { margin: 0.5rem 0; padding-left: 0.8rem; border-left: 2px dashed var(--rule); }
  .rev { margin-bottom: 0.6rem; opacity: 0.85; }
  .comments { margin-top: 0.6rem; padding-top: 0.5rem; border-top: 1px solid var(--rule); font-family: var(--font-ui); font-size: 0.85rem; }
  .comment { margin-bottom: 0.4rem; }
  .comment .who { font-weight: 600; }
  .comment p { margin: 0.1rem 0 0; white-space: pre-wrap; }
  .reply { display: flex; gap: 0.4rem; }
  .reply input { flex: 1; font-size: 0.85rem; padding: 0.3rem 0.5rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  .danger { color: var(--danger); }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.7rem; padding: 0 0.2rem; }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0; font-size: 0.8rem; }
  .small { font-size: 0.8rem; }
</style>
