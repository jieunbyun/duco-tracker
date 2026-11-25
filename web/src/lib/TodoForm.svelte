<script lang="ts">
  import { untrack } from "svelte";
  import { saveTodo, deleteTodo, saveSlot, saveProject, saveMilestone, loadTodoNotes, addIdeaNote, saveIdeaNote, deleteIdeaNote, saveNoteOrder } from "./data";
  import type { Taxonomy, Project, Todo, Slot, TodoFields, IdeaNote } from "./data";
  import { addDays, fmtDay } from "./dates";
  import { undoable } from "./undo.svelte";
  import { LIVE_STATUSES } from "./horizon";
  import Linked from "./Linked.svelte";
  import Sortable from "./Sortable.svelte";

  type Props = {
    todo: Todo | null; // null = new
    slots: Slot[]; // this to-do's sittings (for a meeting: its one sitting)
    tax: Taxonomy;
    projects: Project[];
    weekStart: string;
    day?: string; // preset day for a new item
    placeOnDay?: boolean; // a new task is also planned onto `day`
    kind?: "task" | "meeting";
    /** what happened, and the ids of any to-dos created (for undo) */
    onsaved: (info: { action: "created" | "updated" | "deleted" | "cancelled" | "restored"; ids?: string[] }) => void;
    oncancel: () => void;
    oncomments?: () => void; // a comment was added, changed or deleted (saved at once)
  };
  let { todo, slots, tax, projects, weekStart, day, placeOnDay, kind: kind0, onsaved, oncancel, oncomments }: Props = $props();

  const init = untrack(() => ({ todo, slots, weekStart, day, kind0, placeOnDay }));
  const t0 = init.todo;
  const meetingSlot = t0?.kind === "meeting" ? init.slots[0] ?? null : null;

  let kind = $state<"task" | "meeting">(t0?.kind === "meeting" ? "meeting" : t0 ? "task" : init.kind0 ?? "task");
  let title = $state(t0?.title ?? "");
  let category_id = $state(t0?.category_id ?? "");
  let project_id = $state(t0?.project_id ?? "");
  let projectSearch = $state("");
  let milestone_id = $state(t0?.milestone_id ?? "");
  // "+ New project…" / "+ New milestone…" in the menus: named here, made when the to-do is saved
  // (a to-do on no project stays on Week alone; one on a project is reached from the Logbook)
  const NEW_PROJECT = "__new_project__";
  const NEW_MILESTONE = "__new__";
  let newProject = $state("");
  let newMilestone = $state({ title: "", due_on: "" });
  // a retry after a failed save reuses what was already made
  let madeProject: { title: string; category: string; id: string } | null = null;
  let madeMilestone: { project: string; title: string; id: string } | null = null;
  let est = $state<number | null>(t0?.est_hours ?? null);
  let must = $state(t0?.must_this_week ?? false);
  let core = $state(t0?.is_core ?? false);
  let note = $state(t0?.note ?? "");
  // a note shows as text, its web addresses as a short "link"; click it to edit
  let noteEditing = $state(!t0?.note);
  let noteClicked = false;
  function editNote(ev: Event) {
    if ((ev.target as HTMLElement).closest("a") || getSelection()?.toString()) return;
    noteClicked = noteEditing = true;
  }
  /** Opened by a click, the box is ready to type, the cursor after what is there. */
  function ready(el: HTMLTextAreaElement) {
    if (!noteClicked) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }
  let due_on = $state(t0?.due_on ?? init.day ?? init.weekStart);
  let date = $state(meetingSlot?.planned_on ?? t0?.due_on ?? init.day ?? init.weekStart);
  let start = $state(meetingSlot?.start_time?.slice(0, 5) ?? "10:00");
  let end = $state(meetingSlot?.end_time?.slice(0, 5) ?? "11:00");
  let repeat = $state(1);
  let busy = $state(false);
  let error = $state("");

  const groups = $derived(tax.areas.map((a) => ({
    area: a,
    cats: tax.allCategories.filter((c) => c.area_id === a.id && (c.is_active || c.id === t0?.category_id)),
  })));
  const projectOptions = $derived.by(() => {
    const query = projectSearch.trim().toLocaleLowerCase();
    return projects
      .filter((p) =>
        (query
          ? p.name.toLocaleLowerCase().includes(query) || p.id === project_id
          : !category_id || p.category_id === category_id) &&
        (LIVE_STATUSES.has(p.status) || p.id === t0?.project_id),
      )
      .sort((a, b) => a.name.localeCompare(b.name));
  });
  const projectMatches = $derived(
    projectOptions.filter((p) => p.name.toLocaleLowerCase().includes(projectSearch.trim().toLocaleLowerCase())),
  );
  const project = $derived(projects.find((p) => p.id === project_id) ?? null);
  const categoryNote = $derived(tax.categories.find((c) => c.id === category_id)?.description ?? "");
  const milestoneOptions = $derived(
    (project?.milestone ?? []).filter((m) => (m.status !== "done" && m.status !== "dropped") || m.id === t0?.milestone_id),
  );

  function onCategory() {
    projectSearch = "";
    if (project_id && project_id !== NEW_PROJECT && !projectOptions.some((p) => p.id === project_id)) project_id = "";
    milestone_id = "";
  }
  function onProject() {
    // a project carries its own category
    if (project) category_id = project.category_id;
    milestone_id = "";
  }
  // picking a milestone works as + From milestones does: an empty title becomes the milestone's
  function onMilestone() {
    const m = milestoneOptions.find((x) => x.id === milestone_id);
    if (m && !title.trim()) title = m.title;
  }

  const hours = (a: string, b: string) => {
    const [ah, am] = a.split(":").map(Number);
    const [bh, bm] = b.split(":").map(Number);
    return Math.round(((bh * 60 + bm - ah * 60 - am) / 60) * 100) / 100;
  };

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!title.trim()) return (error = "Give it a title.");
    if (kind === "meeting" && !(start && end && end > start)) return (error = "The meeting must end after it starts.");
    if (project_id === NEW_PROJECT && !newProject.trim()) return (error = "Name the new project.");
    if (project_id === NEW_PROJECT && !category_id) return (error = "Choose a category for the new project.");
    if (milestone_id === NEW_MILESTONE && !newMilestone.title.trim()) return (error = "Name the new milestone.");
    busy = true;
    error = "";
    const created: string[] = [];
    try {
      let proj = project_id || null;
      if (project_id === NEW_PROJECT) {
        const name = newProject.trim();
        if (madeProject?.title !== name || madeProject.category !== category_id) {
          const id = await saveProject(null, {
            name, category_id, status: "active", start_on: null, end_on: null, planned_hours: null,
            is_important: false, notes: null, folder_url: null,
          });
          madeProject = { title: name, category: category_id, id };
          madeMilestone = null;
        }
        proj = madeProject!.id;
      }
      let milestone = milestone_id || null;
      if (milestone_id === NEW_MILESTONE && proj) {
        const name = newMilestone.title.trim();
        if (madeMilestone?.project !== proj || madeMilestone.title !== name) {
          const id = await saveMilestone(null, {
            project_id: proj, title: name, status: "active", start_on: null,
            due_on: newMilestone.due_on || null, planned_hours: null, hard_deadline: false,
            sort_order: (Math.max(0, ...(project?.milestone ?? []).map((m) => m.sort_order)) + 10), notes: null,
          });
          madeMilestone = { project: proj, title: name, id };
        }
        milestone = madeMilestone!.id;
      }
      const base: Partial<TodoFields> = {
        kind,
        title: title.trim(),
        category_id: category_id || null,
        project_id: proj,
        milestone_id: milestone,
        is_core: core,
        note: note.trim() || null,
      };
      if (kind === "task") {
        const id = await saveTodo(t0?.id ?? null, { ...base, due_on, est_hours: est ?? null, must_this_week: must });
        created.push(id);
        if (!t0 && init.placeOnDay && init.day) {
          await saveSlot(null, { todo_id: id, planned_on: init.day, planned_hours: null });
        }
      } else {
        const len = hours(start, end);
        const times = { start_time: start, end_time: end, planned_hours: len };
        if (t0) {
          await saveTodo(t0.id, { ...base, due_on: date, est_hours: len });
          if (meetingSlot) await saveSlot(meetingSlot.id, { planned_on: date, ...times });
          else await saveSlot(null, { todo_id: t0.id, planned_on: date, ...times });
        } else {
          for (let i = 0; i < Math.max(1, repeat); i++) {
            const d = addDays(date, 7 * i);
            const id = await saveTodo(null, { ...base, due_on: d, est_hours: len, must_this_week: true });
            created.push(id);
            await saveSlot(null, { todo_id: id, planned_on: d, ...times });
          }
        }
      }
      onsaved(t0 ? { action: "updated" } : { action: "created", ids: created });
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  // ---- comments: dated, newest first, each saved at once (as on a Logbook action) -----------
  let comments = $state<IdeaNote[]>([]);
  let commentText = $state("");
  let commentEdit = $state<{ id: string; body: string } | null>(null);
  let commentBusy = $state(false);
  async function loadComments() {
    if (t0) comments = await loadTodoNotes(t0.id).catch(() => [] as IdeaNote[]);
  }
  loadComments();
  async function commentAct(label: string, run: () => Promise<unknown>): Promise<boolean> {
    commentBusy = true;
    try {
      await undoable(label, run);
      await loadComments();
      oncomments?.();
      return true;
    } catch (err) {
      error = (err as Error).message;
      return false;
    } finally {
      commentBusy = false;
    }
  }
  async function addComment() {
    const body = commentText.trim();
    if (!t0 || !body) return;
    if (await commentAct(`Commented on “${t0.title}”`, () => addIdeaNote(t0.id, body))) commentText = "";
  }
  async function keepComment() {
    const e = commentEdit;
    if (!e || !t0) return;
    const was = comments.find((c) => c.id === e.id);
    if (!e.body.trim() || e.body.trim() === was?.body) return void (commentEdit = null);
    if (await commentAct(`Changed a comment on “${t0.title}”`, () => saveIdeaNote(e.id, e.body.trim()))) commentEdit = null;
  }
  function removeComment(c: IdeaNote) {
    if (!t0 || !confirm("Delete this comment?")) return;
    commentEdit = null;
    commentAct(`Deleted a comment on “${t0.title}”`, () => deleteIdeaNote(c.id));
  }
  // Enter adds (or keeps an edit) rather than saving the whole form; Shift+Enter starts a new line
  function commentKeys(ev: KeyboardEvent, run: () => unknown) {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); run(); }
    if (ev.key === "Escape" && commentEdit) { ev.preventDefault(); ev.stopPropagation(); commentEdit = null; }
  }
  async function reorderComments(ids: string[]) {
    if (!t0) return;
    const was = new Map(comments.map((c) => [c.id, c.sort_order]));
    comments = ids.map((id) => comments.find((c) => c.id === id)!); // at once; the reload confirms it
    const ok = await commentAct(`Reordered the comments on “${t0.title}”`, () => saveNoteOrder(ids, was));
    if (ok) return;
    await loadComments(); // back as they were
    if (/sort_order/.test(error)) error = "Reordering comments needs web/db/0073_note_order.sql run first, in the Supabase SQL editor.";
  }
  function startCommentEdit(ev: Event, c: IdeaNote) {
    if ((ev.target as HTMLElement).closest("a") || getSelection()?.toString()) return;
    commentEdit = { id: c.id, body: c.body };
  }

  async function remove() {
    if (!t0 || !confirm(`Delete “${t0.title}”${t0.kind === "task" ? " and its planned days" : ""}? Logged time stays.`)) return;
    busy = true;
    try {
      await deleteTodo(t0.id);
      onsaved({ action: "deleted" });
    } catch (err) {
      error = (err as Error).message;
      busy = false;
    }
  }

  async function toggleCancelled() {
    if (!t0) return;
    busy = true;
    try {
      await saveTodo(t0.id, { is_cancelled: !t0.is_cancelled });
      onsaved({ action: t0.is_cancelled ? "restored" : "cancelled" });
    } catch (err) {
      error = (err as Error).message;
      busy = false;
    }
  }
</script>

<form class="todo-form" onsubmit={save}>
  {#if !t0}
    <div class="kind wide" role="group" aria-label="Kind">
      <button type="button" class:on={kind === "task"} aria-pressed={kind === "task"} onclick={() => (kind = "task")}>Duty / to-do</button>
      <button type="button" class:on={kind === "meeting"} aria-pressed={kind === "meeting"} onclick={() => (kind = "meeting")}>Meeting</button>
    </div>
  {/if}

  <label class="wide">Title <input bind:value={title} placeholder={kind === "meeting" ? "e.g. DD weekly" : "e.g. Referee report for RESS"} /></label>

  <label>
    Category
    <select bind:value={category_id} onchange={onCategory}>
      <option value="">— none —</option>
      {#each groups as g (g.area.id)}
        <optgroup label={g.area.label}>
          {#each g.cats as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
        </optgroup>
      {/each}
    </select>
  </label>
  <label class="wide">Search all Planning projects
    <input type="search" bind:value={projectSearch} placeholder="Find a project by name" autocomplete="off" />
  </label>
  <label>
    Project
    <select bind:value={project_id} onchange={onProject}>
      <option value="">— none (on Week only) —</option>
      {#each projectOptions as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
      <option value={NEW_PROJECT}>+ New project…</option>
    </select>
    {#if projectSearch.trim() && !projectMatches.length}<span class="project-empty">No matching projects</span>{/if}
  </label>
  {#if project_id === NEW_PROJECT}
    <label>New project <input bind:value={newProject} placeholder="its name, in Planning" /></label>
  {/if}
  {#if categoryNote}<p class="hint">{categoryNote}</p>{/if}
  {#if project_id}
    <label>
      Milestone
      <select bind:value={milestone_id} onchange={onMilestone}>
        <option value="">— none —</option>
        {#each milestoneOptions as m (m.id)}<option value={m.id}>{m.title}</option>{/each}
        <option value={NEW_MILESTONE}>+ New milestone…</option>
      </select>
    </label>
    {#if milestone_id === NEW_MILESTONE}
      <label>New milestone <input bind:value={newMilestone.title} placeholder="its name, on {project?.name ?? (newProject.trim() || 'the new project')}" /></label>
      <label>Milestone due <input type="date" bind:value={newMilestone.due_on} /></label>
    {/if}
  {/if}

  {#if kind === "task"}
    <label>Week of <input type="date" bind:value={due_on} required /></label>
    <label>Estimated hours <input type="number" min="0" step="0.5" bind:value={est} /></label>
    <label class="check"><input type="checkbox" bind:checked={must} /> Must do this week</label>
  {:else}
    <label>Date <input type="date" bind:value={date} required /></label>
    <label>Start <input type="time" step="300" bind:value={start} required /></label>
    <label>End <input type="time" step="300" bind:value={end} required /></label>
    {#if !t0}
      <label>Repeat weekly <select bind:value={repeat}>
        {#each [1, 2, 3, 4, 6, 8, 10, 12] as n (n)}<option value={n}>{n === 1 ? "no" : `${n} weeks`}</option>{/each}
      </select></label>
    {/if}
  {/if}
  <label class="check"><input type="checkbox" bind:checked={core} /> 🎯 Core</label>
  {#if noteEditing}
    <label class="wide">Note
      <textarea rows="2" bind:value={note} use:ready placeholder="optional — paste a web address and it shows as a short “link”"></textarea>
    </label>
  {:else}
    <div class="wide note">
      <span class="note-head">Note <button type="button" class="mini" onclick={editNote}>Edit</button></span>
      <span class="note-text" role="button" tabindex="0" title="Click to edit" onclick={editNote}
            onkeydown={(ev) => { if (ev.target === ev.currentTarget && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); editNote(ev); } }}><Linked text={note} /></span>
    </div>
  {/if}

  {#if t0}
    <div class="wide comments">
      <span class="note-head">Comments{#if comments.length} <span class="count">{comments.length}</span>{/if}</span>
      <textarea class="comment-add" rows="1" bind:value={commentText} disabled={commentBusy} aria-label="Add a comment"
                placeholder="Add a comment — Enter adds it (saved at once); a web address shows as a short “link”"
                onkeydown={(ev) => commentKeys(ev, addComment)}></textarea>
      {#if comments.length}
        <div class="comment-list">
          <Sortable items={comments} onreorder={reorderComments} disabled={commentBusy || !!commentEdit}>
          {#snippet row(c)}
            <div class="comment">
              <span class="when">{fmtDay(c.created_at.slice(0, 10))}</span>
              {#if commentEdit?.id === c.id}
                <span class="comment-edit">
                  <textarea rows="2" bind:value={commentEdit.body} aria-label="Comment" disabled={commentBusy}
                            onkeydown={(ev) => commentKeys(ev, keepComment)}></textarea>
                  <span class="comment-actions">
                    <button type="button" class="mini" onclick={keepComment} disabled={commentBusy}>Keep</button>
                    <button type="button" class="mini" onclick={() => (commentEdit = null)}>Cancel</button>
                    <button type="button" class="mini danger" onclick={() => removeComment(c)} disabled={commentBusy}>Delete</button>
                  </span>
                </span>
              {:else}
                <span class="note-text" role="button" tabindex="0" title="Click to change or delete"
                      onclick={(ev) => startCommentEdit(ev, c)}
                      onkeydown={(ev) => { if (ev.target === ev.currentTarget && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); startCommentEdit(ev, c); } }}><Linked text={c.body} /></span>
              {/if}
            </div>
          {/snippet}
          </Sortable>
        </div>
      {/if}
    </div>
  {/if}

  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{t0 ? "Save" : kind === "meeting" ? "Add meeting" : "Add to-do"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if t0}
      <button type="button" class="push" onclick={toggleCancelled} disabled={busy}>{t0.is_cancelled ? "Restore" : "Cancel this to-do"}</button>
      <button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>
    {/if}
  </div>
</form>

<style>
  .todo-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
    gap: 0.7rem 1rem;
    font-family: var(--font-ui);
  }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .note { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .note-text {
    justify-self: start; cursor: text; font-size: 0.92rem; color: var(--ink); white-space: pre-line; overflow-wrap: anywhere;
    border-radius: var(--radius); padding: 0.1rem 0.3rem; margin-left: -0.3rem;
  }
  .note-text:hover, .note-text:focus-visible { background: var(--panel); }
  .note-head { display: flex; align-items: center; gap: 0.5rem; }
  .mini { font-size: 0.75rem; padding: 0.1rem 0.5rem; }
  .comments { display: grid; gap: 0.35rem; font-size: 0.82rem; color: var(--ink-soft); }
  .comments .count { font-size: 0.75rem; }
  .comment-list { max-height: 14rem; overflow-y: auto; }
  .comment { display: flex; gap: 0.6rem; align-items: baseline; padding: 0.1rem 0; }
  .comments .when { flex: none; font-size: 0.75rem; font-variant-numeric: tabular-nums; }
  .comment-edit { flex: 1; display: grid; gap: 0.3rem; }
  .comment-actions { display: flex; gap: 0.35rem; }
  .hint { grid-column: 1 / -1; margin: -0.35rem 0 0; font-size: 0.8rem; color: var(--ink-soft); white-space: pre-line; }
  .project-empty { font-size: 0.8rem; color: var(--ink-soft); }

  .kind { display: flex; }
  .kind button { font-size: 0.85rem; border-radius: 0; }
  .kind button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
  .kind button:last-child { border-radius: 0 var(--radius) var(--radius) 0; border-left: none; }
  .kind button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .check { display: flex; align-items: center; gap: 0.45rem; align-self: end; padding-bottom: 0.5rem; color: var(--ink); font-size: 0.88rem; }
  .check input { width: auto; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .push { margin-left: auto; }
  .danger { color: var(--danger); }
</style>
