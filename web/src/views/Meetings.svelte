<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = { selected: null as string | null, query: "" };
</script>

<script lang="ts">
  // Meetings: your meeting logs, one series per log (as your .tex files were). A meeting is
  // planned with its agenda — tied, if you like, to its entry on the Week calendar, each
  // leading to the other — and kept with what was discussed and the actions; the actions
  // not yet done go to Week; search across them all; and .tex out and in.
  import {
    loadAll, saveSeries, deleteSeries, saveMeeting, deleteMeeting, importLog, sendToWeek, parseTex, toTex, downloadTex,
    AGENDA, DISCUSSION, ACTIONS, OTHERS, isAction, isOthers, isAgenda, tickField, linesOf, calendarBetween, calendarFor, addToCalendar,
  } from "../lib/meetings";
  import type { Series, Meeting, Section, ParsedLog, CalendarEntry } from "../lib/meetings";
  import BackLink from "../lib/BackLink.svelte";
  import { tick } from "svelte";
  import { loadProjects } from "../lib/data";
  import type { Project } from "../lib/data";
  import { undoable } from "../lib/undo.svelte";
  import { fmtDay, today, weekStart } from "../lib/dates";

  let series = $state<Series[]>([]);
  let meetings = $state<Meeting[]>([]);
  let projects = $state<Project[]>([]);
  let missing = $state(false);
  let loading = $state(true);
  let error = $state("");
  let selected = $state<string | null>(last.selected);
  let query = $state(last.query);
  let opened = $state(false); // on a phone: the series is showing instead of the list
  let canLink = $state(true); // false until 0064 is run
  let cal = $state(new Map<string, CalendarEntry>()); // the linked calendar entries, by to-do
  let flash = $state<string | null>(null); // a meeting lit up for a moment, arrived at from Week

  // from Week: #/meetings?m=<meeting>&back=…  or  ?new=1&todo=<to-do>&date=…&title=…&back=…
  const arrived = new URLSearchParams(location.hash.split("?")[1] ?? "");
  const back = /^#\/week(\?[\w=&%.-]*)?$/.test(arrived.get("back") ?? "") ? arrived.get("back") : null;
  let goTo = arrived.get("m");
  let fromCalendar = arrived.get("new") && arrived.get("todo")
    ? { todo: arrived.get("todo")!, date: arrived.get("date") ?? today(), title: arrived.get("title") ?? "" } : null;
  if (arrived.size) history.replaceState(null, "", "#/meetings");

  $effect(() => {
    Object.assign(last, { selected, query });
  });

  async function load() {
    try {
      const [all, p] = await Promise.all([loadAll(), loadProjects().catch(() => [] as Project[])]);
      missing = all === null;
      series = all?.series ?? [];
      meetings = all?.meetings ?? [];
      canLink = all?.canLink ?? true;
      projects = p;
      cal = await calendarFor([...new Set(meetings.map((m) => m.todo_id).filter((x): x is string => !!x))]).catch(() => new Map());
      if (!selected || !series.some((s) => s.id === selected)) selected = series[0]?.id ?? null;
      error = "";
      arrive();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  /** Arrived from Week: show that meeting, or start one for that calendar entry. */
  async function arrive() {
    if (goTo) {
      const m = meetings.find((x) => x.id === goTo);
      goTo = null;
      if (!m) return;
      selected = m.series_id;
      query = "";
      opened = true;
      flash = m.id;
      await tick();
      document.querySelector(`[data-meeting="${m.id}"]`)?.scrollIntoView({ block: "center" });
      setTimeout(() => (flash = null), 2500);
    } else if (fromCalendar) {
      const c = fromCalendar;
      fromCalendar = null;
      if (!series.length) return void (error = "Add a series first (+ New series), then come back from the calendar to start its agenda.");
      opened = true;
      newMeeting({ date: c.date, title: c.title, todo: c.todo });
      // its time, to show while you write the agenda
      const found = await calendarFor([c.todo]).catch(() => new Map<string, CalendarEntry>());
      cal = new Map([...cal, ...found]);
    }
  }

  async function act(label: string, run: () => Promise<unknown>): Promise<boolean> {
    try {
      await undoable(label, run);
      await load();
      return true;
    } catch (e) {
      error = `Not saved: ${(e as Error).message}`;
      return false;
    }
  }

  const current = $derived(series.find((s) => s.id === selected) ?? null);
  const ofSeries = (id: string) => meetings.filter((m) => m.series_id === id);
  const countOf = (id: string) => ofSeries(id).length;
  const lastMet = (id: string) => ofSeries(id)[0]?.met_on ?? null;
  const seriesName = (id: string) => series.find((s) => s.id === id)?.name ?? "";
  const projectName = (id: string | null) => projects.find((p) => p.id === id)?.name ?? "";

  // ---- search: every word, anywhere in a meeting -----------------------------------------
  const words = $derived(query.toLowerCase().split(/\s+/).filter(Boolean));
  const haystack = (m: Meeting) =>
    [m.title, m.people, m.met_on, fmtDay(m.met_on), seriesName(m.series_id), ...m.sections.flatMap((s) => [s.heading, s.body])]
      .join(" ").toLowerCase();
  const found = $derived(words.length ? meetings.filter((m) => words.every((w) => haystack(m).includes(w))) : []);

  // ---- a series ----------------------------------------------------------------------
  let seriesForm = $state<{ id: string | null; name: string; project_id: string | null } | null>(null);
  function editSeries(s: Series | null) {
    seriesForm = { id: s?.id ?? null, name: s?.name ?? "", project_id: s?.project_id ?? null };
  }
  async function keepSeries(ev: SubmitEvent) {
    ev.preventDefault();
    const f = seriesForm!;
    const name = f.name.trim();
    if (!name) return;
    let id = f.id;
    if (await act(f.id ? "Changed meeting series" : "Added meeting series", async () => {
      id = await saveSeries(f.id, { name, headings: [AGENDA, DISCUSSION, ACTIONS, OTHERS], project_id: f.project_id });
    })) {
      seriesForm = null;
      selected = id;
      opened = true;
    }
  }
  function removeSeries(s: Series) {
    const n = countOf(s.id);
    if (!confirm(`Delete “${s.name}”${n ? ` and its ${n} ${n === 1 ? "meeting" : "meetings"}` : ""}? (Undo brings it back.)`)) return;
    act("Deleted meeting series", () => deleteSeries(s.id));
  }
  function exportSeries(s: Series) {
    downloadTex(`${s.name.replace(/[\\/:*?"<>|]/g, "")}.tex`, toTex(s, ofSeries(s.id)));
  }

  // ---- a meeting -----------------------------------------------------------------------
  type Draft = {
    id: string | null; series_id: string; met_on: string; title: string; people: string; sections: Section[];
    todo_id: string | null; newCal: { start: string; end: string } | null; // newCal: add it to the calendar on saving
  };
  let draft = $state<Draft | null>(null);
  const blankSections = (): Section[] => [AGENDA, DISCUSSION, ACTIONS, OTHERS].map((heading) => ({ heading, body: "" }));
  function newMeeting(from?: { date: string; title: string; todo: string }) {
    choices = null;
    draft = {
      id: null, series_id: selected ?? series[0]?.id ?? "", met_on: from?.date ?? today(), title: from?.title ?? "", people: "",
      sections: blankSections(), todo_id: from?.todo ?? null, newCal: null,
    };
  }
  function editMeeting(m: Meeting) {
    choices = null;
    draft = {
      id: m.id, series_id: m.series_id, met_on: m.met_on, title: m.title ?? "", people: m.people ?? "",
      sections: structuredClone($state.snapshot(m.sections)), todo_id: m.todo_id ?? null, newCal: null,
    };
  }
  async function keepMeeting() {
    const d = draft!;
    if (!d.series_id) return void (error = "Pick a series for the meeting.");
    const fields = {
      series_id: d.series_id, met_on: d.met_on, title: d.title.trim() || null, people: d.people.trim() || null,
      sections: d.sections.map((x) => ({ ...x, body: x.body.replace(/\s+$/, "") })),
    };
    let id = d.id;
    if (await act(d.id ? "Changed meeting" : "Added meeting", async () => {
      let todo = d.todo_id;
      if (d.newCal) todo = await addToCalendar(fields.title ?? seriesName(d.series_id), d.met_on, d.newCal.start, d.newCal.end);
      id = await saveMeeting(d.id, canLink ? { ...fields, todo_id: todo } : fields);
    })) {
      draft = null;
      selected = d.series_id;
      flash = id;
      setTimeout(() => (flash = null), 1500);
    }
  }

  // ---- the calendar entry: one of the day's meetings in Week, or a new one ----------------------
  let choices = $state<CalendarEntry[] | null>(null);
  async function findOnCalendar() {
    try {
      choices = await calendarBetween(draft!.met_on, draft!.met_on);
    } catch (e) {
      error = (e as Error).message;
    }
  }
  const hhmm = (t: string | null) => (t ? t.slice(0, 5) : "");
  const when = (c: CalendarEntry) => `${fmtDay(c.day)}${c.start ? ` ${hhmm(c.start)}${c.end ? `–${hhmm(c.end)}` : ""}` : ""}`;
  /** To Week, at the meeting's week, with the meeting picked out; Week's Back comes here. */
  function toCalendar(m: Meeting) {
    const c = cal.get(m.todo_id!);
    if (!c) return;
    history.replaceState(null, "", "#/meetings");
    location.hash = `#/week?w=${weekStart(c.day)}&show=${m.todo_id}&agenda=${m.id}`;
  }
  const upcoming = (m: Meeting) => m.met_on >= today();

  // tick boxes: the agenda's items, ticked off on the day, and the actions, ticked off when done
  function tickLine(m: Meeting, si: number, line: string) {
    const s = m.sections[si];
    const field = tickField(s.heading)!;
    const had = s[field] ?? [];
    const next = had.includes(line) ? had.filter((x) => x !== line) : [...had, line];
    const sections = m.sections.map((y, i) => (i === si ? { ...y, [field]: next } : y));
    meetings = meetings.map((x) => (x.id === m.id ? { ...x, sections } : x)); // at once; the reload confirms it
    const what = isAgenda(s.heading) ? "an agenda item" : "an action";
    act(had.includes(line) ? `Unticked ${what}` : `Ticked ${what}`, () => saveMeeting(m.id, { sections }));
  }
  function removeMeeting(m: Meeting) {
    if (!confirm(`Delete the meeting of ${fmtDay(m.met_on)}${m.title ? ` (${m.title})` : ""}? (Undo brings it back.)`)) return;
    act("Deleted meeting", () => deleteMeeting(m.id));
  }

  // ---- the actions not yet done ---------------------------------------------------------------
  type Todo = { m: Meeting; si: number; line: string };
  const openOf = (which: (h: string) => boolean): Todo[] => current ? ofSeries(current.id).flatMap((m) => m.sections.flatMap((s, si) =>
    which(s.heading) ? linesOf(s.body).filter((l) => !s.sent?.includes(l)).map((line) => ({ m, si, line })) : [])) : [];
  const toDo = $derived(openOf(isAction)); // yours
  const waiting = $derived(openOf(isOthers)); // others'

  function withSection(m: Meeting, si: number, change: (s: Section) => Section): Section[] {
    return m.sections.map((s, i) => (i === si ? change({ ...s }) : s));
  }
  async function handled(t: Todo, toWeek: boolean) {
    const note = `From the meeting of ${fmtDay(t.m.met_on)}: ${seriesName(t.m.series_id)}${t.m.title ? ` — ${t.m.title}` : ""}`;
    await act(toWeek ? `Sent “${t.line}” to Week` : `Ticked off “${t.line}”`, async () => {
      if (toWeek) await sendToWeek(t.line, note);
      await saveMeeting(t.m.id, { sections: withSection(t.m, t.si, (s) => ({ ...s, sent: [...(s.sent ?? []), t.line] })) });
    });
  }

  // ---- import ----------------------------------------------------------------------------
  type Incoming = ParsedLog & { file: string; into: string | null };
  let incoming = $state<Incoming[] | null>(null);
  let importing = $state(false);
  async function readFiles(ev: Event) {
    const input = ev.currentTarget as HTMLInputElement;
    const files = [...(input.files ?? [])];
    input.value = "";
    const logs: Incoming[] = [];
    for (const f of files) {
      const log = parseTex(await f.text(), f.name);
      const same = series.find((s) => s.name.trim().toLowerCase() === log.name.trim().toLowerCase());
      logs.push({ ...log, file: f.name, into: same?.id ?? null });
    }
    incoming = logs;
  }
  // meetings already there (the same date and title) are not added twice
  const fresh = (l: Incoming) => !l.into ? l.meetings
    : l.meetings.filter((m) => !ofSeries(l.into!).some((x) => x.met_on === m.met_on && (x.title ?? "") === (m.title ?? "")));
  async function doImport() {
    const logs = incoming!;
    importing = true;
    let first: string | null = null;
    const ok = await act(`Imported ${logs.length} meeting ${logs.length === 1 ? "log" : "logs"}`, async () => {
      for (const l of logs) {
        if (l.into) {
          for (const m of fresh(l)) await saveMeeting(null, { ...m, series_id: l.into });
          first ??= l.into;
        } else {
          const id = await importLog(l);
          first ??= id;
        }
      }
    });
    importing = false;
    if (ok) {
      incoming = null;
      selected = first;
    }
  }

  // ---- showing a section's text: lines, "- " bullets (nested by indent), [links](https://…) ----
  const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
  function inline(s: string): string {
    return escapeHtml(s).replace(/\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g, (_, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t || u}</a>`);
  }
  function rich(body: string, bullets = false): string {
    let html = "";
    let depth = 0;
    for (const raw of body.split("\n")) {
      if (!raw.trim()) continue;
      // with bullets: a plain line is a bullet too
      const m = raw.match(/^(\s*)-\s+(.*)$/) ?? (bullets ? (["", "", raw.trim()] as unknown as RegExpMatchArray) : null);
      const want = m ? Math.floor(m[1].replace(/\t/g, "  ").length / 2) + 1 : 0;
      while (depth < want) { html += "<ul>"; depth++; }
      while (depth > want) { html += "</ul>"; depth--; }
      html += m ? `<li>${inline(m[2])}</li>` : `<p>${inline(raw.trim())}</p>`;
    }
    while (depth--) html += "</ul>";
    return html;
  }
</script>

{#if back}<BackLink href={back} text="Back to Week" />{/if}

<section class="meetings" class:opened>
  <div class="head">
    <div>
      <span class="eyebrow">Meetings</span>
      <h1>Meeting logs</h1>
    </div>
    {#if !missing}
      <span class="head-acts">
        <label class="file-btn">Import .tex…<input type="file" accept=".tex,text/x-tex" multiple onchange={readFiles} /></label>
        <button class="primary" onclick={() => editSeries(null)}>+ New series</button>
      </span>
    {/if}
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if missing}
    <p class="muted">Meetings needs its tables first: run <code>web/db/0060_meetings.sql</code> in the Supabase SQL editor, then reload.</p>
  {:else}
    {#if seriesForm}
      <form class="panel series-form" onsubmit={keepSeries}>
        <label>Name <input bind:value={seriesForm.name} required placeholder="e.g. Byeongseong Choi, or General meetings" /></label>
        <label>Project <span class="muted small">(optional)</span>
          <select bind:value={seriesForm.project_id}>
            <option value={null}>None</option>
            {#each projects as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
          </select>
        </label>
        <div class="buttons">
          <button class="primary" type="submit">{seriesForm.id ? "Save" : "Add series"}</button>
          <button type="button" onclick={() => (seriesForm = null)}>Cancel</button>
        </div>
      </form>
    {/if}

    {#if incoming}
      <div class="panel import">
        <h2>Import</h2>
        {#each incoming as l, i (i)}
          {@const n = fresh(l).length}
          <div class="import-row">
            <strong>{l.file}</strong>
            <label>Series name <input bind:value={l.name} disabled={!!l.into} /></label>
            {#if series.length}
              <label>Into
                <select bind:value={l.into}>
                  <option value={null}>A new series</option>
                  {#each series as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
                </select>
              </label>
            {/if}
            <span class="muted small">
              {n} {n === 1 ? "meeting" : "meetings"} to add{l.meetings.length - n ? ` · ${l.meetings.length - n} already there` : ""}{l.meetings.length ? ` · ${fmtDay(l.meetings[l.meetings.length - 1].met_on)} – ${fmtDay(l.meetings[0].met_on)}` : ""}{l.skipped.length ? ` · left out (no date): ${l.skipped.join(", ")}` : ""}
            </span>
          </div>
        {/each}
        <div class="buttons">
          <button class="primary" disabled={importing || !incoming.some((l) => fresh(l).length || !l.into)} onclick={doImport}>{importing ? "Importing…" : "Import"}</button>
          <button onclick={() => (incoming = null)}>Cancel</button>
        </div>
      </div>
    {/if}

    <div class="panes">
      <aside class="list">
        <input type="search" bind:value={query} placeholder="Search all meetings…" aria-label="Search all meetings" />
        <ul>
          {#each series as s (s.id)}
            <li>
              <button class:sel={s.id === selected && !words.length} onclick={() => { selected = s.id; query = ""; opened = true; draft = null; }}>
                <span class="name">{s.name}</span>
                <span class="muted small">{countOf(s.id)} · {lastMet(s.id) ? fmtDay(lastMet(s.id)!) : "none yet"}</span>
              </button>
            </li>
          {/each}
        </ul>
        {#if !series.length}
          <p class="muted small">No series yet. Import your .tex logs, or start a series: one for each person or group you meet regularly, and one for everything else.</p>
        {/if}
      </aside>

      <div class="detail">
        <button class="back" onclick={() => { opened = false; query = ""; }}>← All series</button>
        {#if words.length}
          <h2>{found.length} {found.length === 1 ? "meeting" : "meetings"} with “{query.trim()}”</h2>
          {#each found as m (m.id)}{@render card(m, true)}{/each}
        {:else if current}
          <div class="series-head">
            <div>
              <h2>{current.name}</h2>
              <span class="muted small">{countOf(current.id)} {countOf(current.id) === 1 ? "meeting" : "meetings"}{current.project_id ? ` · ${projectName(current.project_id)}` : ""}</span>
            </div>
            <span class="tools">
              <button class="primary" onclick={() => newMeeting()}>+ Meeting</button>
              <button onclick={() => exportSeries(current)} title="Download as a .tex file, laid out as your logs are">Export .tex</button>
              <button onclick={() => editSeries(current)}>Edit</button>
              <button class="del" onclick={() => removeSeries(current)}>Delete</button>
            </span>
          </div>

          {#if toDo.length || waiting.length}
            <div class="follow">
              {#if toDo.length}
                <div>
                  <span class="eyebrow">My open actions</span>
                  <ul>
                    {#each toDo as t (`${t.m.id}|${t.si}|${t.line}`)}
                      <li>
                        <span class="what">{t.line} <span class="muted small">· {fmtDay(t.m.met_on)}</span></span>
                        <span class="acts">
                          <button class="mini" title="Add it to this week's to-dos in Week" onclick={() => handled(t, true)}>→ Week</button>
                          <button class="mini" title="Done, or no longer needed: off this list" onclick={() => handled(t, false)}>✓</button>
                        </span>
                      </li>
                    {/each}
                  </ul>
                </div>
              {/if}
              {#if waiting.length}
                <div>
                  <span class="eyebrow">Waiting on others</span>
                  <ul>
                    {#each waiting as t (`${t.m.id}|${t.si}|${t.line}`)}
                      <li>
                        <span class="what">{t.line} <span class="muted small">· {fmtDay(t.m.met_on)}</span></span>
                        <span class="acts"><button class="mini" title="Done: off this list" onclick={() => handled(t, false)}>✓</button></span>
                      </li>
                    {/each}
                  </ul>
                </div>
              {/if}
            </div>
          {/if}

          {#if draft && !draft.id}{@render editor()}{/if}
          {@const ahead = ofSeries(current.id).filter(upcoming).sort((a, b) => a.met_on.localeCompare(b.met_on))}
          {#if ahead.length}
            <h3 class="group">Coming up</h3>
            {#each ahead as m (m.id)}{@render card(m, false)}{/each}
            {#if ofSeries(current.id).length > ahead.length}<h3 class="group">Past</h3>{/if}
          {/if}
          {#each ofSeries(current.id).filter((m) => !upcoming(m)) as m (m.id)}{@render card(m, false)}{/each}
          {#if !countOf(current.id) && !draft}
            <p class="muted">No meetings in this series yet.</p>
          {/if}
        {:else if series.length}
          <p class="muted">Pick a series on the left.</p>
        {/if}
      </div>
    </div>
  {/if}
</section>

{#snippet card(m: Meeting, withSeries: boolean)}
  {#if draft?.id === m.id}
    {@render editor()}
  {:else}
    <article class="meeting" class:ahead={upcoming(m)} class:flash={flash === m.id} data-meeting={m.id}>
      <div class="m-head">
        <span class="date">{fmtDay(m.met_on)}</span>
        {#if upcoming(m)}<span class="badge">{m.met_on === today() ? "Today" : "Upcoming"}</span>{/if}
        {#if m.title}<strong>{m.title}</strong>{/if}
        {#if m.people}<span class="muted small">with {m.people}</span>{/if}
        {#if withSeries}<button class="link small" onclick={() => { selected = m.series_id; query = ""; }}>{seriesName(m.series_id)}</button>{/if}
        {#if m.todo_id}
          {@const c = cal.get(m.todo_id)}
          {#if c}<button class="link small cal" title="Open it on the Week calendar" onclick={() => toCalendar(m)}>📅 {when(c)} ›</button>
          {:else}<span class="muted small">📅 calendar entry gone</span>{/if}
        {/if}
        <span class="tools">
          <button class="mini" onclick={() => { if (withSeries) { selected = m.series_id; query = ""; } editMeeting(m); }}>Edit</button>
          <button class="mini del" onclick={() => removeMeeting(m)}>Delete</button>
        </span>
      </div>
      {#each m.sections as s, si (si)}
        {#if s.body.trim()}
          <div class="sec">
            <span class="heading">{s.heading}</span>
            {#if tickField(s.heading)}
              {@const f = tickField(s.heading)!}
              <ul class="agenda">
                {#each linesOf(s.body) as line (line)}
                  <li class:done={s[f]?.includes(line)}>
                    <label><input type="checkbox" checked={!!s[f]?.includes(line)} onchange={() => tickLine(m, si, line)} />
                      <span>{@html inline(line)}</span></label>
                  </li>
                {/each}
              </ul>
            {:else}
              <div class="body">{@html rich(s.body, true)}</div>
            {/if}
          </div>
        {/if}
      {/each}
    </article>
  {/if}
{/snippet}

{#snippet editor()}
  {#if draft}
    <form class="panel meeting-form" onsubmit={(ev) => { ev.preventDefault(); keepMeeting(); }}>
      <div class="row">
        {#if !draft.id && series.length > 1}
          <label>Series
            <select bind:value={draft.series_id}>{#each series as x (x.id)}<option value={x.id}>{x.name}</option>{/each}</select>
          </label>
        {/if}
        <label>Date <input type="date" bind:value={draft.met_on} required onchange={() => (choices = null)} /></label>
        <label class="grow">Title <input bind:value={draft.title} placeholder="e.g. PhD interview, or Bi-weekly meeting" /></label>
        <label class="grow">With <input bind:value={draft.people} placeholder="Who was there (optional)" /></label>
      </div>
      {#if canLink}
        <div class="cal-row">
          <span class="sec-head">Calendar</span>
          {#if draft.todo_id}
            {@const c = cal.get(draft.todo_id) ?? choices?.find((x) => x.todo_id === draft!.todo_id)}
            <span>📅 {c ? `${c.title} · ${when(c)}` : "linked to a calendar entry"}</span>
            <button type="button" class="link small" onclick={() => (draft!.todo_id = null)}>Unlink</button>
          {:else if draft.newCal}
            <span>📅 New on {fmtDay(draft.met_on)}</span>
            <input type="time" bind:value={draft.newCal.start} aria-label="Starts" />–<input type="time" bind:value={draft.newCal.end} aria-label="Ends" />
            <button type="button" class="link small" onclick={() => (draft!.newCal = null)}>Cancel</button>
          {:else if choices}
            <span class="choices">
              {#each choices as c (c.todo_id + c.day)}
                <button type="button" class="chip" onclick={() => { draft!.todo_id = c.todo_id; cal = new Map(cal).set(c.todo_id, c); if (!draft!.title) draft!.title = c.title; }}>
                  {hhmm(c.start)} {c.title}</button>
              {:else}<span class="muted small">Nothing on the calendar on {fmtDay(draft.met_on)}.</span>{/each}
              <button type="button" class="link small" onclick={() => (draft!.newCal = { start: "10:00", end: "11:00" })}>+ Add to the calendar</button>
            </span>
          {:else}
            <button type="button" class="link small" onclick={findOnCalendar}>Link to the calendar…</button>
          {/if}
        </div>
      {/if}
      {#each draft.sections as s (s.heading)}
        <label class="sec-edit">
          <span class="sec-head">{s.heading}<span class="muted small">{isAction(s.heading) ? " · one a line, each a tick box; it can go to Week"
            : isOthers(s.heading) ? " · one a line, each a tick box" : isAgenda(s.heading) ? " · one item a line, each a tick box for the day"
            : " · one point a line, each a bullet (“  - ” nests one)"}</span></span>
          <textarea rows={isAction(s.heading) || isOthers(s.heading) ? 2 : isAgenda(s.heading) ? 3 : 4} bind:value={s.body}
                    placeholder={isAction(s.heading) ? "e.g. Send the HPC request" : isOthers(s.heading) ? "e.g. RH: check the EQ inputs"
                      : isAgenda(s.heading) ? "e.g. Results on the larger graph" : "e.g. ShakeMap added; layout revised"}></textarea>
        </label>
      {/each}
      <div class="buttons">
        <button class="primary" type="submit">{draft.id ? "Save" : "Add meeting"}</button>
        <button type="button" onclick={() => (draft = null)}>Cancel</button>
      </div>
    </form>
  {/if}
{/snippet}

<style>
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .head h1 { margin: 0; }
  .head-acts { display: flex; gap: 0.5rem; align-items: center; }
  .file-btn { border: 1px solid var(--rule); background: var(--panel); border-radius: var(--radius); padding: 0.45rem 0.9rem; cursor: pointer; font-family: var(--font-ui); font-size: 0.9rem; }
  .file-btn input { display: none; }
  .small { font-size: 0.8rem; }
  .link { background: none; border: none; padding: 0; color: var(--accent); cursor: pointer; font: inherit; }
  .panel { background: var(--panel); border-radius: var(--radius); padding: 0.9rem; display: grid; gap: 0.6rem; margin-bottom: 1rem; }
  .panel h2 { margin: 0; font-size: 1.1rem; }
  .panel label { display: grid; gap: 0.25rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  .buttons { display: flex; gap: 0.5rem; }
  .import-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr); gap: 0.3rem 0.8rem; align-items: end; padding-bottom: 0.6rem; border-bottom: 1px solid var(--rule); }
  .import-row strong { grid-column: 1 / -1; font-family: var(--font-ui); font-size: 0.88rem; }
  .import-row > span { grid-column: 1 / -1; }

  .panes { display: grid; grid-template-columns: minmax(0, 16rem) minmax(0, 1fr); gap: 1.5rem; align-items: start; }
  .list { position: sticky; top: 4rem; display: grid; gap: 0.5rem; font-family: var(--font-ui); }
  .list ul { list-style: none; margin: 0; padding: 0; }
  .list li button { width: 100%; display: grid; gap: 0.05rem; text-align: left; background: none; border: none; border-radius: var(--radius); padding: 0.45rem 0.55rem; }
  .list li button:hover { background: var(--panel); }
  .list li button.sel { background: var(--panel); box-shadow: inset 3px 0 0 var(--accent); }
  .name { font-weight: 600; font-size: 0.9rem; }
  .back { display: none; margin-bottom: 0.8rem; }

  .series-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 0.6rem; margin-bottom: 0.8rem; }
  .series-head h2 { margin: 0; }
  .tools { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .tools button { font-size: 0.82rem; padding: 0.3rem 0.7rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.5rem; }
  .del { color: var(--danger); }

  .follow { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: 0.8rem 1.2rem; background: var(--panel); border-radius: var(--radius); padding: 0.7rem 0.9rem; margin-bottom: 1rem; }
  .follow ul { list-style: none; margin: 0.3rem 0 0; padding: 0; display: grid; gap: 0.25rem; }
  .follow li { display: flex; gap: 0.5rem; align-items: baseline; justify-content: space-between; font-size: 0.9rem; }
  .follow .acts { display: flex; gap: 0.25rem; flex-shrink: 0; }

  .meeting { border-top: 1px solid var(--rule); padding: 0.8rem 0; display: grid; gap: 0.45rem; }
  .meeting.ahead { background: var(--panel); border-radius: var(--radius); border-top: none; padding: 0.8rem; margin-bottom: 0.5rem; }
  .meeting.flash { animation: lit 2.5s ease-out; }
  @keyframes lit { 0%, 40% { box-shadow: 0 0 0 3px var(--accent); } 100% { box-shadow: 0 0 0 3px transparent; } }
  .badge { font-family: var(--font-ui); font-size: 0.7rem; font-weight: 600; color: var(--accent-ink); background: var(--accent); border-radius: 999px; padding: 0.05rem 0.5rem; }
  .cal { font-family: var(--font-ui); }
  h3.group { font-size: 0.95rem; margin: 1rem 0 0.4rem; color: var(--ink-soft); }
  .agenda { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.2rem; }
  .agenda label { display: flex; gap: 0.45rem; align-items: flex-start; cursor: pointer; font-size: 0.93rem; }
  .agenda input { width: auto; margin-top: 0.25rem; flex-shrink: 0; }
  .agenda li.done span { text-decoration: line-through; color: var(--ink-soft); }
  .cal-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.6rem; font-size: 0.9rem; }
  .cal-row input[type="time"] { width: auto; padding: 0.2rem 0.3rem; }
  .choices { display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .chip { font-size: 0.8rem; padding: 0.15rem 0.6rem; border-radius: 999px; background: none; font-family: var(--font-ui); }
  .m-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.3rem 0.7rem; }
  .m-head .tools { margin-left: auto; }
  .date { font-family: var(--font-ui); font-size: 0.82rem; color: var(--ink-soft); font-variant-numeric: tabular-nums; }
  .sec { display: grid; grid-template-columns: 9rem minmax(0, 1fr); gap: 0.8rem; }
  .heading { font-family: var(--font-ui); font-size: 0.78rem; font-weight: 600; color: var(--ink-soft); padding-top: 0.15rem; }
  .body { font-size: 0.93rem; overflow-wrap: anywhere; }
  .body :global(p) { margin: 0 0 0.25rem; }
  .body :global(ul) { margin: 0 0 0.25rem; padding-left: 1.1rem; }
  .body :global(li) { margin: 0.05rem 0; }

  .meeting-form .row { display: flex; flex-wrap: wrap; gap: 0.6rem; }
  .meeting-form .row label:first-child { width: 10rem; }
  .meeting-form .grow { flex: 1; min-width: 12rem; }
  .sec-edit { display: grid; gap: 0.2rem; }
  .sec-head { font-family: var(--font-ui); font-size: 0.82rem; font-weight: 600; color: var(--ink-soft); }

  textarea { color: var(--ink); resize: vertical; field-sizing: content; min-height: 2.6rem; }

  @media (max-width: 48rem) {
    .panes { grid-template-columns: 1fr; }
    .list { position: static; }
    .meetings.opened .list, .meetings:not(.opened) .detail { display: none; }
    .back { display: inline-block; }
    .sec { grid-template-columns: 1fr; gap: 0.1rem; }
    .import-row { grid-template-columns: 1fr; }
  }
</style>
