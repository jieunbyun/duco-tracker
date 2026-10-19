<script lang="ts">
  import { loadProjects } from "../lib/data";
  import type { Project } from "../lib/data";
  import {
    STATUSES, KINDS, loadReadings, loadNotes, saveNote, deleteNote, uploadPdf, pdfLink, removePdf,
    citationOf, bibtexOf, fmtSize,
  } from "../lib/reading";
  import type { Reading, Note } from "../lib/reading";
  import { fmtDay, today } from "../lib/dates";
  import ReadingForm from "../lib/ReadingForm.svelte";

  const FREE_STORAGE = 1024 * 1024 * 1024; // Supabase's free plan: 1 GB of files

  let items = $state<Reading[]>([]);
  let projects = $state<Project[]>([]);
  let loading = $state(true);
  let error = $state("");
  let adding = $state(false);
  let open = $state<string | null>(null); // the item shown in full
  let editing = $state(false);
  let filter = $state("all");
  let search = $state("");

  async function load() {
    try {
      [items, projects] = await Promise.all([loadReadings(), loadProjects()]);
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  const shown = $derived.by(() => {
    const q = search.trim().toLowerCase();
    return items.filter((r) =>
      (filter === "all" || r.status === filter) &&
      (!q || [r.title, r.authors, r.venue, r.doi].some((v) => v?.toLowerCase().includes(q))));
  });
  const groups = $derived(
    STATUSES.map((s) => ({ ...s, rows: shown.filter((r) => r.status === s.key) })).filter((g) => g.rows.length),
  );
  const storageUsed = $derived(items.reduce((s, r) => s + (r.pdf_size ?? 0), 0));
  const projectName = (id: string | null) => (id ? projects.find((p) => p.id === id)?.name ?? "" : "");
  const kindLabel = (k: string) => KINDS.find((x) => x.key === k)?.label ?? k;
  const noteCount = (r: Reading) => r.reading_note?.[0]?.count ?? 0;

  function byline(r: Reading): string {
    const names = (r.authors ?? "").split(";").map((s) => s.split(",")[0].trim()).filter(Boolean);
    const who = names.length > 2 ? `${names[0]} et al.` : names.join(" & ");
    return [who, r.year, r.venue].filter(Boolean).join(" · ");
  }
  function period(r: Reading): string {
    if (!r.started_on && !r.finished_on) return "";
    if (r.started_on && r.finished_on) return `${fmtDay(r.started_on)} – ${fmtDay(r.finished_on)}`;
    return r.started_on ? `since ${fmtDay(r.started_on)}` : `finished ${fmtDay(r.finished_on!)}`;
  }

  function toggle(r: Reading) {
    editing = false;
    adding = false;
    if (open === r.id) {
      open = null;
      return;
    }
    open = r.id;
    notes = [];
    loadNotes(r.id).then((n) => { if (open === r.id) notes = n; }).catch((e) => (error = e.message));
  }

  async function saved(id: string) {
    adding = false;
    editing = false;
    await load();
    if (open !== id) {
      open = id;
      notes = await loadNotes(id).catch(() => []);
    }
  }

  // ---- notes -------------------------------------------------------------------------
  let notes = $state<Note[]>([]);
  let noteDate = $state(today());
  let notePage = $state("");
  let noteBody = $state("");
  let noteEditing = $state<string | null>(null);
  let noteBusy = $state(false);

  async function addNote(r: Reading) {
    if (!noteBody.trim()) return;
    noteBusy = true;
    try {
      await saveNote(noteEditing, { reading_id: r.id, noted_on: noteDate || today(), page: notePage.trim() || null, body: noteBody.trim() });
      noteBody = "";
      notePage = "";
      noteDate = today();
      noteEditing = null;
      notes = await loadNotes(r.id);
      await load();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      noteBusy = false;
    }
  }
  function editNote(n: Note) {
    noteEditing = n.id;
    noteDate = n.noted_on;
    notePage = n.page ?? "";
    noteBody = n.body;
  }
  async function removeNote(r: Reading, n: Note) {
    if (!confirm("Delete this note?")) return;
    try {
      await deleteNote(n.id);
      notes = await loadNotes(r.id);
      await load();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  // ---- PDF ---------------------------------------------------------------------------
  let pdfBusy = $state(false);
  async function onPdf(r: Reading, ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    pdfBusy = true;
    try {
      await uploadPdf(r, file);
      await load();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      pdfBusy = false;
    }
  }
  async function openPdf(r: Reading) {
    // open the tab first (pop-up blockers allow it), then point it at the signed link
    const tab = window.open("", "_blank");
    try {
      const url = await pdfLink(r);
      if (tab) tab.location.href = url;
      else window.location.href = url;
    } catch (e) {
      tab?.close();
      error = (e as Error).message;
    }
  }
  async function dropPdf(r: Reading) {
    if (!confirm(`Remove the PDF of “${r.title}”?`)) return;
    pdfBusy = true;
    try {
      await removePdf(r);
      await load();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      pdfBusy = false;
    }
  }

  // ---- copy ---------------------------------------------------------------------------
  let copied = $state("");
  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      copied = what;
      setTimeout(() => (copied = ""), 2000);
    } catch {
      copied = "";
    }
  }
</script>

<section class="reading">
  <span class="eyebrow">Reading</span>
  <h1>Reading</h1>

  <div class="toolbar">
    {#if !adding}<button class="primary" onclick={() => { adding = true; open = null; }}>+ Add reading</button>{/if}
    <div class="filters" role="group" aria-label="Show">
      {#each [{ key: "all", label: "All" }, ...STATUSES] as s (s.key)}
        <button class:on={filter === s.key} aria-pressed={filter === s.key} onclick={() => (filter = s.key)}>{s.label}</button>
      {/each}
    </div>
    <input class="search" type="search" bind:value={search} placeholder="Search title, authors, journal, DOI" aria-label="Search" />
  </div>
  {#if storageUsed}
    <p class="muted small">PDFs: {fmtSize(storageUsed)} of 1 GB free storage ({Math.round((100 * storageUsed) / FREE_STORAGE)}%)</p>
  {/if}

  {#if error}<p class="error">{error}</p>{/if}

  {#if adding}
    <div class="card"><ReadingForm reading={null} {projects} onsaved={saved} oncancel={() => (adding = false)} /></div>
  {/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if !items.length && !adding}
    <p class="muted">Nothing recorded yet. Add a journal article or book — a DOI fills in the details.</p>
  {:else if !shown.length}
    <p class="muted">Nothing matches.</p>
  {/if}

  {#each groups as g (g.key)}
    <h2>{g.label} <span class="muted count">{g.rows.length}</span></h2>
    <ul class="items">
      {#each g.rows as r (r.id)}
        <li class:open={open === r.id}>
          <button class="row" onclick={() => toggle(r)} aria-expanded={open === r.id}>
            <span class="what">
              <strong class="title">{r.title}</strong>
              <span class="by muted">{byline(r)}</span>
            </span>
            <span class="meta muted">
              {kindLabel(r.kind)}{period(r) ? ` · ${period(r)}` : ""}
              {#if noteCount(r)} · {noteCount(r)} {noteCount(r) === 1 ? "note" : "notes"}{/if}
              {#if r.pdf_path} · PDF{/if}
              {#if r.project_id} · {projectName(r.project_id)}{/if}
            </span>
          </button>

          {#if open === r.id}
            <div class="body">
              {#if editing}
                <ReadingForm reading={r} {projects} onsaved={saved} ondeleted={async () => { open = null; await load(); }}
                             oncancel={() => (editing = false)} />
              {:else}
                <div class="links">
                  {#if r.doi}<a href={`https://doi.org/${r.doi}`} target="_blank" rel="noopener">doi.org/{r.doi}</a>{/if}
                  {#if r.url && !r.doi}<a href={r.url} target="_blank" rel="noopener">{r.url}</a>{/if}
                  <button class="mini" onclick={() => (editing = true)}>Edit details</button>
                </div>

                <div class="cite">
                  <h3>Citation</h3>
                  <p class="ref">{citationOf(r)}</p>
                  <div class="cite-acts">
                    <button class="mini" onclick={() => copy(citationOf(r), "citation")}>{copied === "citation" ? "Copied" : "Copy citation"}</button>
                    <button class="mini" onclick={() => copy(bibtexOf(r), "bibtex")}>{copied === "bibtex" ? "Copied" : "Copy BibTeX"}</button>
                  </div>
                </div>

                <div class="pdf">
                  <h3>PDF</h3>
                  {#if r.pdf_path}
                    <button class="mini" onclick={() => openPdf(r)}>Open PDF</button>
                    <span class="muted small">{fmtSize(r.pdf_size)}</span>
                    <label class="mini file">Replace<input type="file" accept="application/pdf,.pdf" onchange={(ev) => onPdf(r, ev)} /></label>
                    <button class="mini danger" onclick={() => dropPdf(r)}>Remove</button>
                  {:else}
                    <label class="mini file">{pdfBusy ? "Uploading…" : "Upload PDF"}<input type="file" accept="application/pdf,.pdf" disabled={pdfBusy} onchange={(ev) => onPdf(r, ev)} /></label>
                    <span class="muted small">up to 50 MB; kept privately in your storage</span>
                  {/if}
                </div>

                <div class="notes">
                  <h3>Notes</h3>
                  <form class="note-form" onsubmit={(ev) => { ev.preventDefault(); addNote(r); }}>
                    <input type="date" bind:value={noteDate} aria-label="Date" />
                    <input class="page" bind:value={notePage} placeholder="page" aria-label="Page" />
                    <textarea rows="3" bind:value={noteBody} placeholder="What you took from it…" aria-label="Note"></textarea>
                    <div class="note-acts">
                      <button class="primary" type="submit" disabled={noteBusy || !noteBody.trim()}>{noteEditing ? "Save note" : "Add note"}</button>
                      {#if noteEditing}<button type="button" onclick={() => { noteEditing = null; noteBody = ""; notePage = ""; noteDate = today(); }}>Cancel</button>{/if}
                    </div>
                  </form>
                  {#each notes as n (n.id)}
                    <div class="note" class:editing={noteEditing === n.id}>
                      <div class="note-head">
                        <span class="muted">{fmtDay(n.noted_on)}{n.page ? ` · p. ${n.page}` : ""}</span>
                        <button class="mini" onclick={() => editNote(n)}>Edit</button>
                        <button class="mini danger" onclick={() => removeNote(r, n)}>Delete</button>
                      </div>
                      <p>{n.body}</p>
                    </div>
                  {:else}
                    <p class="muted small">No notes yet.</p>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/each}
</section>

<style>
  .toolbar { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin: 0.8rem 0; font-family: var(--font-ui); }
  .filters { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .filters button { font-size: 0.82rem; padding: 0.3rem 0.65rem; }
  .filters button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .search { width: auto; flex: 1; min-width: 12rem; max-width: 24rem; }
  .small { font-size: 0.8rem; font-family: var(--font-ui); }
  .card { background: var(--panel); border-radius: var(--radius); padding: 1rem; margin-bottom: 1rem; }
  .reading h2 { margin-top: 1.6rem; font-size: 1.1rem; }
  .count { font-size: 0.85rem; font-weight: 400; }
  .items { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; font-family: var(--font-ui); }
  .items li { border-radius: var(--radius); }
  .items li.open { background: var(--panel); }
  .row {
    width: 100%; display: grid; gap: 0.15rem; text-align: left; background: none; border: none;
    border-radius: var(--radius); padding: 0.55rem 0.6rem;
  }
  .row:hover { background: var(--panel); }
  .what { display: grid; gap: 0.1rem; }
  .title { font-size: 0.95rem; }
  .by, .meta { font-size: 0.8rem; }
  .body { padding: 0.3rem 0.8rem 1rem; display: grid; gap: 1rem; }
  .links { display: flex; flex-wrap: wrap; gap: 0.8rem; align-items: center; font-size: 0.85rem; }
  .body h3 { font-size: 0.9rem; margin: 0 0 0.3rem; }
  .ref { margin: 0 0 0.4rem; font-family: var(--font); font-size: 0.95rem; }
  .cite-acts, .pdf { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
  .pdf h3 { width: 100%; }
  .mini { font-size: 0.78rem; padding: 0.2rem 0.55rem; }
  .file { position: relative; display: inline-block; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--panel); cursor: pointer; }
  .file input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .danger { color: var(--danger); }
  .note-form { display: grid; grid-template-columns: 10rem 6rem 1fr; gap: 0.4rem; margin-bottom: 0.6rem; }
  .note-form textarea { grid-column: 1 / -1; }
  .note-acts { grid-column: 1 / -1; display: flex; gap: 0.4rem; }
  .note { border-top: 1px solid var(--rule); padding: 0.45rem 0; }
  .note.editing { opacity: 0.5; }
  .note-head { display: flex; gap: 0.4rem; align-items: center; font-size: 0.8rem; }
  .note-head .muted { margin-right: auto; }
  .note p { margin: 0.2rem 0 0; white-space: pre-line; font-size: 0.9rem; }
  @media (max-width: 40rem) { .note-form { grid-template-columns: 1fr 1fr; } }
</style>
