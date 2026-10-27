<script lang="ts">
  // A member's project's milestones, set the way your Planning milestones are:
  // start and due dates, what each comes after (dates it does not set itself are
  // implied from those, then from the project), a hard deadline and notes. Each
  // person sets the hours they plan to put in, seen by nobody else. A milestone is public
  // (everyone on the project) or private (only whoever made it), chosen when it
  // is made; it comes after milestones of its own kind only.
  import { saveMilestone, deleteMilestone, saveMyMilestoneHours } from "./group";
  import { fmtHours } from "./data";
  import type { GroupProject, GroupMilestone, Member } from "./group";
  import { impliedDates } from "./plan";
  import type { DateSource } from "./plan";
  import { fmtDay, today } from "./dates";
  import Sortable from "./Sortable.svelte";

  type Props = {
    project: GroupProject; milestones: GroupMilestone[]; members?: Member[]; readonly?: boolean;
    act: (f: () => Promise<unknown>) => Promise<boolean>;
  };
  let { project, milestones, members = [], readonly = false, act }: Props = $props();
  // a public milestone's lead: one of the people on the project (a label only)
  const nameOf = (id: string) => members.find((x) => x.user_id === id)?.display_name ?? "—";
  const people = $derived(members.filter((x) => project.members.includes(x.user_id) || x.role === "supervisor"));

  // Which row is open for editing: a milestone id, "new", or nothing.
  let editing = $state<string | null>(null);
  let draft = $state(blank());
  let error = $state("");

  function blank() {
    return { title: "", start_on: "", due_on: "", hard_deadline: false, notes: "", after: [] as string[], is_private: false,
             hours: null as number | null, lead: "" };
  }
  function open(m: GroupMilestone | null) {
    if (readonly) return;
    error = "";
    editing = m?.id ?? "new";
    draft = m
      ? { title: m.title, start_on: m.start_on ?? "", due_on: m.due_on ?? "", hard_deadline: m.hard_deadline,
          notes: m.notes ?? "", after: m.after_ids.filter((id) => milestones.some((x) => x.id === id)), is_private: m.is_private,
          hours: m.my_hours, lead: m.lead_id ?? "" }
      : blank();
  }

  async function save(event: SubmitEvent, m: GroupMilestone | null) {
    event.preventDefault();
    if (draft.start_on && draft.due_on && draft.due_on < draft.start_on) return (error = "The due date is before the start date.");
    const before = milestones.find((x) => draft.after.includes(x.id) && x.due_on && draft.due_on && x.due_on > draft.due_on);
    if (before) return (error = `It is due before “${before.title}”, which it comes after.`);
    error = "";
    const order = m?.sort_order ?? Math.max(0, ...milestones.map((x) => x.sort_order)) + 10;
    const hours = typeof draft.hours === "number" && !Number.isNaN(draft.hours) ? draft.hours : null;
    const ok = await act(async () => {
      const id = await saveMilestone(m?.id ?? null, {
      project_id: project.id,
      ...(!m && draft.is_private ? { is_private: true } : {}),
      title: draft.title.trim(),
      start_on: draft.start_on || null,
      due_on: draft.due_on || null,
      hard_deadline: draft.hard_deadline,
      notes: draft.notes.trim() || null,
      after_ids: draft.after,
      // only sent when there is something to say, so saving works before 0043 is run
      ...(draft.lead || m?.lead_id ? { lead_id: draft.is_private ? null : draft.lead || null } : {}),
      sort_order: order,
      });
      if (hours !== (m?.my_hours ?? null)) await saveMyMilestoneHours(id, hours);
    });
    if (ok) editing = null; // on failure the form stays, with what was typed
  }
  async function remove(m: GroupMilestone) {
    if (!confirm(`Delete the milestone “${m.title}”?`)) return;
    if (await act(() => deleteMilestone(m.id))) editing = null;
  }
  // drag the ⠿ handle to put them in order (saved as 10, 20, 30…; only those that moved)
  async function reorder(ids: string[]) {
    await act(async () => {
      for (const [i, id] of ids.entries()) {
        const order = (i + 1) * 10;
        if (milestones.find((x) => x.id === id)?.sort_order !== order) await saveMilestone(id, { sort_order: order });
      }
    });
  }
  const tick = (m: GroupMilestone) => act(() => saveMilestone(m.id, { done: !m.done, done_on: m.done ? null : today() }));

  // the project's end: its own, else the last milestone due
  const projectEnd = $derived(project.end_on ?? (milestones.map((m) => m.due_on).filter((d): d is string => !!d).sort().at(-1) ?? null));
  const datesOf = (m: GroupMilestone) => impliedDates(milestones, m, project.start_on, projectEnd);

  // the milestones this one can come after: any other of its kind, except those that (in turn) come after it
  function laterThan(id: string): Set<string> {
    const out = new Set<string>();
    const walk = (x: string) => {
      for (const n of milestones) if (n.after_ids.includes(x) && !out.has(n.id)) { out.add(n.id); walk(n.id); }
    };
    walk(id);
    return out;
  }
  const candidates = (m: GroupMilestone | null) => {
    const later = m ? laterThan(m.id) : new Set<string>();
    return milestones.filter((x) => x.id !== m?.id && !later.has(x.id) && x.is_private === draft.is_private);
  };
  // changing the kind of a new one clears what it came after (those were of the other kind)
  function setKind(p: boolean) {
    draft.is_private = p;
    draft.after = [];
  }
  const titleOf = (id: string) => milestones.find((x) => x.id === id)?.title ?? "";
  const why = (from: DateSource, m: GroupMilestone, end: "start" | "due") =>
    from === "after"
      ? end === "start"
        ? `when ${m.after_ids.map(titleOf).filter(Boolean).join(", ")} ${m.after_ids.length > 1 ? "are" : "is"} due`
        : "when the next milestone starts"
      : from === "project" ? `the project's ${end === "start" ? "start" : "end"}` : "";
</script>

{#snippet form(m: GroupMilestone | null)}
  <form class="ms-form" onsubmit={(e) => save(e, m)}>
    <label class="wide">Title <input bind:value={draft.title} required /></label>
    <label>Start <input type="date" bind:value={draft.start_on} /></label>
    <label>Due <input type="date" bind:value={draft.due_on} min={draft.start_on || undefined} /></label>
    <label title="Only you see this">Your hours <input type="number" min="0" step="0.5" bind:value={draft.hours} /></label>
    <label class="check"><input type="checkbox" bind:checked={draft.hard_deadline} /> Hard deadline</label>
    {#if !draft.is_private && people.length}
      <label>Lead
        <select bind:value={draft.lead}>
          <option value="">— none —</option>
          {#each people as x (x.user_id)}<option value={x.user_id}>{x.display_name}</option>{/each}
        </select>
      </label>
    {/if}
    {#if m}
      <p class="kind wide">{m.is_private ? "🔒 Private — only you see it, and what you link to it." : "Public — everyone on the project sees it."}</p>
    {:else}
      <fieldset class="wide kind-pick">
        <legend>Visible to</legend>
        <label class="check"><input type="radio" name="kind" checked={!draft.is_private} onchange={() => setKind(false)} /> Everyone on the project</label>
        <label class="check"><input type="radio" name="kind" checked={draft.is_private} onchange={() => setKind(true)} /> Only me</label>
        <span class="hint">— set now, and it stays. Actions and logbook entries on a private milestone are seen only by you.</span>
      </fieldset>
    {/if}
    {#if candidates(m).length}
      <fieldset class="wide after">
        <legend>Comes after <span class="hint">— with no start date, it starts when the last of these is due</span></legend>
        {#each candidates(m) as x (x.id)}
          <label class="check"><input type="checkbox" value={x.id} bind:group={draft.after} /> {x.title}</label>
        {/each}
      </fieldset>
    {/if}
    <label class="wide">Notes <textarea rows="2" bind:value={draft.notes}></textarea></label>
    {#if error}<p class="error wide">{error}</p>{/if}
    <div class="actions wide">
      <button class="primary" type="submit" disabled={!draft.title.trim()}>{m ? "Save" : "Add milestone"}</button>
      <button type="button" onclick={() => (editing = null)}>Cancel</button>
      {#if m}<button type="button" class="danger" onclick={() => remove(m)}>Delete</button>{/if}
    </div>
  </form>
{/snippet}

{#snippet line(m: GroupMilestone)}
          {#if editing === m.id}
            {@render form(m)}
          {:else}
            {@const d = datesOf(m)}
            <div class="ms-line" class:complete={m.done}>
              <button class="ms-row" onclick={() => open(m)} disabled={readonly} title={readonly ? "" : "Click to edit"}>
                <span class="title">
                  {#if m.is_private}<span class="lock" title="Private — only you see it">🔒</span>{/if}
                  {m.title}
                  {#if m.lead_id && !m.is_private}<small class="after-of">lead: {nameOf(m.lead_id)}</small>{/if}
                  {#if m.hard_deadline}<small class="hard">hard deadline</small>{/if}
                  {#if m.after_ids.some(titleOf)}<small class="after-of">after {m.after_ids.map(titleOf).filter(Boolean).join(", ")}</small>{/if}
                  {#if m.done && m.done_on}<small class="after-of">done {fmtDay(m.done_on)}</small>{/if}
                </span>
                <span class="dates muted">
                  <!-- dates it does not set itself are implied (in italics), and say where from -->
                  <span class:implied={d.startFrom !== "own"} title={why(d.startFrom, m, "start")}>{d.start ? fmtDay(d.start) : "…"}</span>
                  –
                  <span class:implied={d.dueFrom !== "own"} title={why(d.dueFrom, m, "due")}>{d.due ? fmtDay(d.due) : "…"}</span>
                  {#if m.my_hours !== null && !readonly}<span class="mine" title="Your hours — only you see them">· {fmtHours(m.my_hours)}</span>{/if}
                  {#if !readonly}<span class="pen" aria-hidden="true">✎</span>{/if}
                </span>
              </button>
              <input type="checkbox" class="done-tick" checked={m.done} disabled={readonly}
                     title={m.done ? "Done — untick to reopen" : "Mark the milestone done"}
                     aria-label={`${m.title} done`} onchange={() => tick(m)} />
            </div>
          {/if}
{/snippet}

<div class="milestones">
  {#if milestones.length}
    <Sortable items={milestones} row={line} onreorder={reorder} disabled={readonly || editing !== null} />
  {:else}
    <p class="muted empty">No milestones yet.</p>
  {/if}

  {#if !readonly}
    {#if editing === "new"}
      {@render form(null)}
    {:else}
      <button class="add" onclick={() => open(null)}>+ Milestone</button>
    {/if}
  {/if}
</div>

<style>
  .milestones { margin-top: 0.4rem; font-family: var(--font-ui); }
  .ms-row {
    width: 100%;
    display: grid;
    grid-template-columns: 1fr 15rem;
    gap: 0.75rem;
    align-items: center;
    text-align: left;
    background: none;
    border: none;
    padding: 0.4rem 0.4rem;
    font-size: 0.88rem;
    color: inherit;
  }
  .ms-row:hover:not(:disabled) { background: var(--paper); }
  .ms-row:disabled { cursor: default; opacity: 1; }
  .ms-line { display: flex; align-items: center; gap: 0.5rem; }
  .ms-line .ms-row { flex: 1; min-width: 0; }
  .done-tick { width: auto; flex: none; margin-right: 0.4rem; }
  .ms-line.complete .title { text-decoration: line-through; color: var(--ink-soft); }
  .title small.hard { margin-left: 0.4rem; color: var(--danger); font-size: 0.72rem; }
  .title small.after-of { margin-left: 0.4rem; color: var(--ink-soft); font-size: 0.72rem; }
  .dates { font-size: 0.8rem; }
  .implied { font-style: italic; opacity: 0.8; }
  .after { border: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 0.2rem 1rem; }
  .after legend { font-size: 0.8rem; color: var(--ink-soft); padding: 0; margin-bottom: 0.2rem; }
  .after .check { padding-bottom: 0; }
  .hint { font-size: 0.75rem; }
  .lock { font-size: 0.75rem; margin-right: 0.15rem; }
  .pen { margin-left: 0.5rem; color: var(--ink-soft); opacity: 0.5; }
  .ms-row:hover .pen { opacity: 1; }
  .mine { margin-left: 0.3rem; }
  .kind { margin: 0; font-size: 0.8rem; color: var(--ink-soft); }
  .kind-pick { border: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 0.2rem 1rem; }
  .kind-pick legend { font-size: 0.8rem; color: var(--ink-soft); padding: 0; margin-bottom: 0.2rem; }
  .kind-pick .check { padding-bottom: 0; }
  .empty { font-size: 0.85rem; margin: 0.2rem 0 0.5rem; }
  .add { margin-top: 0.4rem; font-size: 0.82rem; }
  .ms-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
    gap: 0.6rem 0.9rem;
    background: var(--paper);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: 0.8rem;
    margin: 0.4rem 0;
  }
  label { display: grid; gap: 0.2rem; font-size: 0.8rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .check { display: flex; align-items: center; gap: 0.45rem; align-self: end; padding-bottom: 0.5rem; color: var(--ink); }
  .check input { width: auto; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
  @media (max-width: 40rem) {
    .ms-row { grid-template-columns: 1fr; }
  }
</style>
