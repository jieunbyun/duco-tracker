<script lang="ts">
  import {
    FIELDS, saveEntry, deleteEntry, deletable, loadRevisions, addComment, deleteComment, parseLinks, linkName,
  } from "./group";
  import type { Entry, EntryKind, GroupProject, Member, Comment, Revision } from "./group";
  import { today, fmtDay } from "./dates";

  type Props = {
    entries: Entry[];
    projects: GroupProject[]; // the projects these entries can be about
    members: Member[];
    comments: Comment[];
    edits: Map<string, number>; // how often each entry was edited
    me: string;
    canWrite: boolean; // the author's own logbook
    onchanged: () => Promise<void>;
  };
  let { entries, projects, members, comments, edits, me, canWrite, onchanged }: Props = $props();

  const nameOf = (id: string) => members.find((m) => m.user_id === id)?.display_name ?? "—";
  const projectOf = (id: string | null) => (id ? projects.find((p) => p.id === id)?.title ?? "(project removed)" : "No project");
  let error = $state("");

  // ---- writing (a new entry, or editing one) ---------------------------------------
  type Draft = { id: string | null; kind: EntryKind; entry_date: string; project_id: string; did: string; results: string; next: string; links: string };
  const blank = (): Draft => ({
    id: null, kind: "entry", entry_date: today(), project_id: projects.find((p) => p.status === "active")?.id ?? "",
    did: "", results: "", next: "", links: "",
  });
  let draft = $state<Draft>(blank());
  let editing = $state<string | null>(null); // id of the entry being edited in place
  let busy = $state(false);

  function startEdit(e: Entry) {
    editing = e.id;
    draft = { id: e.id, kind: e.kind, entry_date: e.entry_date, project_id: e.project_id ?? "", did: e.did ?? "",
              results: e.results ?? "", next: e.next ?? "", links: e.links.join("\n") };
  }
  async function save(ev: SubmitEvent) {
    ev.preventDefault();
    if (!draft.did.trim() && !draft.results.trim() && !draft.next.trim()) return (error = "Write something first.");
    busy = true;
    error = "";
    try {
      await saveEntry(draft.id, {
        kind: draft.kind, entry_date: draft.entry_date || today(), project_id: draft.project_id || null,
        did: draft.did.trim() || null, results: draft.results.trim() || null, next: draft.next.trim() || null,
        links: parseLinks(draft.links),
      });
      const kind = draft.kind, project = draft.project_id;
      draft = { ...blank(), kind, project_id: project };
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
        <select bind:value={draft.project_id}>
          <option value="">No project</option>
          {#each projects as p (p.id)}<option value={p.id}>{p.title}</option>{/each}
        </select>
      </label>
    </div>
    <label>{FIELDS[draft.kind].did} <textarea rows="3" bind:value={draft.did}></textarea></label>
    <label>{FIELDS[draft.kind].results} <textarea rows="2" bind:value={draft.results}></textarea></label>
    <label>{FIELDS[draft.kind].next} <textarea rows="2" bind:value={draft.next}></textarea></label>
    <label>Links — files and folders on OneDrive, one per line
      <textarea rows="2" bind:value={draft.links} placeholder="https://…sharepoint.com/…"></textarea>
    </label>
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
        <span class="muted">· {projectOf(e.project_id)}</span>
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
  <p class="muted">{canWrite ? "No entries yet. Write the first one above — a few lines a day is plenty." : "No entries yet."}</p>
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
  .seg { display: inline-flex; }
  .seg button { font-size: 0.82rem; padding: 0.35rem 0.7rem; border-radius: 0; }
  .seg button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
  .seg button:last-child { border-radius: 0 var(--radius) var(--radius) 0; margin-left: -1px; }
  .seg button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
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
