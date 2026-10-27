<script lang="ts">
  import { loadProjects } from "../lib/data";
  import type { Project } from "../lib/data";
  import {
    STATUSES, KINDS, loadReadings, loadNotes, saveNote, deleteNote, setPdfUrl, pdfLink, removePdf, prunePdfs,
    citationOf, bibtexOf, fmtSize, loadQuotes, shortCite, quoteText,
  } from "../lib/reading";
  import type { Reading, Note, QuoteRow } from "../lib/reading";
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
  let view = $state<"items" | "quotes">("items"); // the reading list, or every quote across it

  async function load() {
    try {
      [items, projects] = await Promise.all([loadReadings(), loadProjects()]);
      error = "";
      prunePdfs(items).catch(() => {}); // files left behind by deletes in earlier sessions
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
  /** "Project › Milestone", or just the project. */
  function linkOf(r: Reading): string {
    const p = r.project_id ? projects.find((x) => x.id === r.project_id) : null;
    if (!p) return "";
    const m = r.milestone_id ? p.milestone.find((x) => x.id === r.milestone_id) : null;
    return m ? `${p.name} › ${m.title}` : p.name;
  }
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

  // ---- notes and quotes ---------------------------------------------------------------
  // A note on its own, or a quote (the words as written) with a note attached.
  let notes = $state<Note[]>([]);
  let noteDate = $state(today());
  let notePage = $state("");
  let noteQuote = $state("");
  let noteBody = $state("");
  let noteEditing = $state<string | null>(null);
  let noteBusy = $state(false);
  const hasQuote = (n: Note) => !!n.quote?.trim();

  function clearNote() {
    noteEditing = null;
    noteQuote = "";
    noteBody = "";
    notePage = "";
    noteDate = today();
  }
  async function addNote(r: Reading) {
    const quote = noteQuote.trim();
    if (!noteBody.trim() && !quote) return;
    const was = noteEditing ? notes.find((n) => n.id === noteEditing) : null;
    noteBusy = true;
    try {
      await saveNote(noteEditing, {
        reading_id: r.id, noted_on: noteDate || today(), page: notePage.trim() || null, body: noteBody.trim() || null,
        ...(quote || was?.quote ? { quote: quote || null } : {}), // (no quote column before 0039)
      });
      clearNote();
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
    noteQuote = n.quote ?? "";
    noteBody = n.body ?? "";
  }
  async function removeNote(r: Reading, n: Note) {
    if (!confirm(hasQuote(n) ? "Delete this quote and its note?" : "Delete this note?")) return;
    try {
      await deleteNote(n.id);
      notes = await loadNotes(r.id);
      await load();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  // ---- every quote ---------------------------------------------------------------------
  let quotes = $state<QuoteRow[]>([]);
  let quotesLoading = $state(false);
  async function showQuotes() {
    view = "quotes";
    adding = false;
    quotesLoading = true;
    try {
      quotes = await loadQuotes();
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      quotesLoading = false;
    }
  }
  const shownQuotes = $derived.by(() => {
    const q = search.trim().toLowerCase();
    return quotes.filter((x) => !q || [x.quote, x.body, x.page, x.reading?.title, x.reading?.authors].some((v) => v?.toLowerCase().includes(q)));
  });
  /** Back to the list, with the reading a quote is from open. */
  function goTo(readingId: string) {
    view = "items";
    filter = "all";
    search = "";
    const r = items.find((x) => x.id === readingId);
    if (r && open !== r.id) toggle(r);
  }

  // ---- PDF ---------------------------------------------------------------------------
  // PDFs live on OneDrive: a reading keeps the link. (Copies stored here before
  // still open, and can be removed once moved.)
  let pdfBusy = $state(false);
  let pdfDraft = $state<Record<string, string>>({});
  async function savePdfUrl(r: Reading, url: string | null) {
    const clean = url?.trim() || null;
    if (clean && !/^https?:\/\//i.test(clean)) return void (error = "Paste the PDF's link from OneDrive (it starts with https://).");
    pdfBusy = true;
    try {
      await setPdfUrl(r, clean);
      pdfDraft[r.id] = "";
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
    {#if !adding && view === "items"}<button class="primary" onclick={() => { adding = true; open = null; }}>+ Add reading</button>{/if}
    <div class="filters" role="group" aria-label="View">
      <button class:on={view === "items"} aria-pressed={view === "items"} onclick={() => (view = "items")}>Readings</button>
      <button class:on={view === "quotes"} aria-pressed={view === "quotes"} onclick={showQuotes}>Quotes</button>
    </div>
    {#if view === "items"}
      <div class="filters" role="group" aria-label="Show">
        {#each [{ key: "all", label: "All" }, ...STATUSES] as s (s.key)}
          <button class:on={filter === s.key} aria-pressed={filter === s.key} onclick={() => (filter = s.key)}>{s.label}</button>
        {/each}
      </div>
    {/if}
    <input class="search" type="search" bind:value={search} aria-label="Search"
           placeholder={view === "quotes" ? "Search quotes, notes, titles, authors" : "Search title, authors, journal, DOI"} />
  </div>
  {#if storageUsed}
    <p class="muted small">PDFs: {fmtSize(storageUsed)} of 1 GB free storage ({Math.round((100 * storageUsed) / FREE_STORAGE)}%)</p>
  {/if}

  {#if error}<p class="error">{error}</p>{/if}

  {#if adding}
    <div class="card"><ReadingForm reading={null} {projects} onsaved={saved} oncancel={() => (adding = false)} /></div>
  {/if}

  {#if view === "quotes"}
    {#if quotesLoading}
      <p class="muted">Loading…</p>
    {:else if !quotes.length}
      <p class="muted">No quotes yet. Open a reading and add one under <em>Notes and quotes</em>.</p>
    {:else if !shownQuotes.length}
      <p class="muted">Nothing matches.</p>
    {:else}
      <div class="quote-acts">
        <span class="muted small">{shownQuotes.length} {shownQuotes.length === 1 ? "quote" : "quotes"}</span>
        <button class="mini" onclick={() => copy(shownQuotes.map((x) => quoteText(x, x.reading)).join("\n\n"), "all-quotes")}>
          {copied === "all-quotes" ? "Copied" : search.trim() ? "Copy these" : "Copy all"}</button>
      </div>
      <ul class="quotes">
        {#each shownQuotes as x (x.id)}
          <li class="note">
            <blockquote>{x.quote}</blockquote>
            {#if x.body}<p class="on-quote">{x.body}</p>{/if}
            <div class="note-head">
              <button class="link muted" onclick={() => goTo(x.reading_id)} title={x.reading?.title ?? ""}>
                {shortCite(x.reading, x.page)} · {fmtDay(x.noted_on)}</button>
              <button class="mini" onclick={() => copy(quoteText(x, x.reading), x.id)}>{copied === x.id ? "Copied" : "Copy"}</button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  {:else if loading}
    <p class="muted">Loading…</p>
  {:else if !items.length && !adding}
    <p class="muted">Nothing recorded yet. Add a journal article or book — a DOI fills in the details.</p>
  {:else if !shown.length}
    <p class="muted">Nothing matches.</p>
  {/if}

  {#each view === "items" ? groups : [] as g (g.key)}
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
              {#if r.pdf_url || r.pdf_path} · PDF{/if}
              {#if linkOf(r)} · {linkOf(r)}{/if}
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
                  {#if r.pdf_url}
                    <a class="mini open" href={r.pdf_url} target="_blank" rel="noopener noreferrer">Open PDF ↗</a>
                    <button class="mini" onclick={() => (pdfDraft[r.id] = r.pdf_url ?? "")}>Change link</button>
                    <button class="mini danger" onclick={() => savePdfUrl(r, null)} disabled={pdfBusy}>Remove link</button>
                  {/if}
                  {#if !r.pdf_url || pdfDraft[r.id]}
                    <form class="pdf-link" onsubmit={(ev) => { ev.preventDefault(); savePdfUrl(r, pdfDraft[r.id] ?? ""); }}>
                      <input type="url" bind:value={pdfDraft[r.id]} placeholder="Paste the PDF's link from OneDrive" aria-label="PDF link" />
                      <button class="mini" type="submit" disabled={pdfBusy || !(pdfDraft[r.id] ?? "").trim()}>Save link</button>
                    </form>
                  {/if}
                  {#if r.pdf_path}
                    <span class="stored muted small">
                      A copy is stored here ({fmtSize(r.pdf_size)}):
                      <button class="mini" onclick={() => openPdf(r)}>Open it</button>
                      {#if r.pdf_url}<button class="mini danger" onclick={() => dropPdf(r)}>Remove the stored copy</button>
                      {:else}— to move it, open it, save it to OneDrive, and paste its link above.{/if}
                    </span>
                  {/if}
                </div>

                <div class="notes">
                  <h3>Notes and quotes
                    {#if notes.some(hasQuote)}
                      <button class="mini" onclick={() => copy(notes.filter(hasQuote).map((n) => quoteText(n, r)).join("\n\n"), "quotes")}>
                        {copied === "quotes" ? "Copied" : "Copy its quotes"}</button>
                    {/if}
                  </h3>
                  <form class="note-form" onsubmit={(ev) => { ev.preventDefault(); addNote(r); }}>
                    <input type="date" bind:value={noteDate} aria-label="Date" />
                    <input class="page" bind:value={notePage} placeholder="page" aria-label="Page" />
                    <textarea class="quote-in" rows="2" bind:value={noteQuote} placeholder="A quote, word for word (optional)" aria-label="Quote"></textarea>
                    <textarea rows="3" bind:value={noteBody} aria-label="Note"
                              placeholder={noteQuote.trim() ? "Your note on the quote (optional)…" : "What you took from it…"}></textarea>
                    <div class="note-acts">
                      <button class="primary" type="submit" disabled={noteBusy || (!noteBody.trim() && !noteQuote.trim())}>
                        {noteEditing ? "Save" : noteQuote.trim() ? "Add quote" : "Add note"}</button>
                      {#if noteEditing}<button type="button" onclick={clearNote}>Cancel</button>{/if}
                    </div>
                  </form>
                  {#each notes as n (n.id)}
                    <div class="note" class:editing={noteEditing === n.id}>
                      <div class="note-head">
                        <span class="muted">{fmtDay(n.noted_on)}{n.page ? ` · p. ${n.page}` : ""}</span>
                        {#if hasQuote(n)}<button class="mini" onclick={() => copy(quoteText(n, r), n.id)}>{copied === n.id ? "Copied" : "Copy"}</button>{/if}
                        <button class="mini" onclick={() => editNote(n)}>Edit</button>
                        <button class="mini danger" onclick={() => removeNote(r, n)}>Delete</button>
                      </div>
                      {#if hasQuote(n)}<blockquote>{n.quote}</blockquote>{/if}
                      {#if n.body}<p class:on-quote={hasQuote(n)}>{n.body}</p>{/if}
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
  .pdf-link { display: flex; gap: 0.4rem; flex: 1; min-width: 16rem; }
  .pdf-link input { flex: 1; font-size: 0.85rem; padding: 0.25rem 0.5rem; }
  .open { text-decoration: none; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--panel); }
  .stored { width: 100%; display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
  .danger { color: var(--danger); }
  .note-form { display: grid; grid-template-columns: 10rem 6rem 1fr; gap: 0.4rem; margin-bottom: 0.6rem; }
  .note-form textarea { grid-column: 1 / -1; }
  .note-acts { grid-column: 1 / -1; display: flex; gap: 0.4rem; }
  .note { border-top: 1px solid var(--rule); padding: 0.45rem 0; }
  .note.editing { opacity: 0.5; }
  .note-head { display: flex; gap: 0.4rem; align-items: center; font-size: 0.8rem; }
  .note-head .muted { margin-right: auto; }
  .note p { margin: 0.2rem 0 0; white-space: pre-line; font-size: 0.9rem; }
  .note-form .quote-in { font-family: var(--font); font-style: italic; }
  blockquote {
    margin: 0.3rem 0 0; padding: 0.1rem 0 0.1rem 0.7rem; border-left: 3px solid var(--rule);
    font-family: var(--font); font-style: italic; font-size: 0.95rem; white-space: pre-line;
  }
  .note p.on-quote { padding-left: 0.85rem; color: var(--ink-soft); }
  .notes h3 { display: flex; gap: 0.6rem; align-items: center; }
  .quote-acts { display: flex; gap: 0.6rem; align-items: center; margin-bottom: 0.4rem; }
  .quotes { list-style: none; margin: 0; padding: 0; font-family: var(--font-ui); }
  .quotes .note-head { margin-top: 0.3rem; }
  .link { background: none; border: none; padding: 0; text-align: left; font-size: 0.8rem; margin-right: auto; cursor: pointer; }
  .link:hover { text-decoration: underline; }
  @media (max-width: 40rem) { .note-form { grid-template-columns: 1fr 1fr; } }
</style>
