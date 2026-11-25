<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = { view: "people" as "people" | "opportunities" | "organisations", selected: null as string | null, tag: null as string | null, query: "", sort: "az" as "az" | "met" };
</script>

<script lang="ts">
  // Network: the people you know (tagged as you like), each time you met them; the
  // opportunities you are watching, by deadline; and the organisations you deal with.
  import {
    loadNetwork, saveContact, saveInteraction, saveOpportunity, saveOrganisation, remove, parseNetwork, importNetwork, splitDated,
  } from "../lib/network";
  import type { Network, Contact, ContactFields, Opportunity, Organisation, ParsedNetwork } from "../lib/network";
  import { readXlsx } from "../lib/xlsx";
  import { undoable } from "../lib/undo.svelte";
  import { fmtDay, today, addDays } from "../lib/dates";
  import { arrivedAt } from "../lib/dayBack.svelte";

  let net = $state<Network>({ contacts: [], interactions: [], opportunities: [], organisations: [] });
  let missing = $state(false);
  let loading = $state(true);
  let error = $state("");
  let view = $state(last.view);
  let selected = $state<string | null>(last.selected);
  let tag = $state<string | null>(last.tag);
  let query = $state(last.query);
  let sort = $state(last.sort);
  let opened = $state(false); // on a phone: the person is showing instead of the list

  $effect(() => {
    Object.assign(last, { view, selected, tag, query, sort });
  });

  async function load() {
    try {
      const n = await loadNetwork();
      missing = n === null;
      if (n) net = n;
      if (!selected || !net.contacts.some((c) => c.id === selected)) selected = null;
      arrive();
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  // from the Day tab (#/network?c=<person>&i=<note>): that person, the note open to change
  const arrived = arrivedAt("network");
  function arrive() {
    const c = arrived.get("c");
    arrived.delete("c");
    if (!c || !net.contacts.some((x) => x.id === c)) return;
    const i = net.interactions.find((x) => x.id === arrived.get("i"));
    Object.assign(last, { view: "people", tag: null, query: "" });
    view = "people";
    tag = null;
    query = "";
    selected = c;
    opened = true;
    draft = null;
    editingMeet = i ? { id: i.id, met_on: i.met_on ?? "", body: i.body } : null;
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

  // ---- people ------------------------------------------------------------------------
  const metOf = (id: string) => net.interactions.filter((i) => i.contact_id === id);
  const lastMet = (id: string) => metOf(id).find((i) => i.met_on)?.met_on ?? null;
  const tags = $derived.by(() => {
    const n = new Map<string, number>();
    for (const c of net.contacts) for (const t of c.tags) n.set(t, (n.get(t) ?? 0) + 1);
    return [...n.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  });
  const words = $derived(query.toLowerCase().split(/\s+/).filter(Boolean));
  const hay = (c: Contact) => [c.name, c.other_name, c.alias, c.country, c.institution, c.unit, c.title, c.email, c.keywords, c.notes,
    ...c.tags, ...metOf(c.id).map((i) => i.body)].join(" ").toLowerCase();
  const people = $derived(net.contacts
    .filter((c) => !tag || c.tags.includes(tag))
    .filter((c) => words.every((w) => hay(c).includes(w)))
    .sort((a, b) => sort === "met" ? (lastMet(b.id) ?? "").localeCompare(lastMet(a.id) ?? "") || a.name.localeCompare(b.name) : a.name.localeCompare(b.name)));
  const person = $derived(net.contacts.find((c) => c.id === selected) ?? null);

  type Draft = Omit<ContactFields, "tags"> & { id: string | null; tags: string };
  let draft = $state<Draft | null>(null);
  const FIELDS: [keyof ContactFields, string, string][] = [
    ["name", "Name", ""], ["other_name", "Other name", "e.g. in Korean, or written differently"], ["alias", "Goes by", ""],
    ["title", "Title", "e.g. Senior Lecturer"], ["institution", "Institution", ""], ["unit", "Department or team", ""],
    ["country", "Country", ""], ["email", "E-mail", ""], ["keywords", "Works on", "e.g. Rail; data science"],
  ];
  function editPerson(c: Contact | null) {
    const base = c ?? { name: query.trim(), other_name: null, alias: null, country: null, institution: null, unit: null, title: null, email: null, keywords: null, notes: null, tags: tag ? [tag] : [] };
    draft = { ...(base as ContactFields), id: c?.id ?? null, tags: base.tags.join(", ") };
    opened = true;
  }
  async function keepPerson(ev: SubmitEvent) {
    ev.preventDefault();
    const d = draft!;
    if (!d.name?.trim()) return;
    const tidy = (v: string | null) => (v?.trim() ? v.trim() : null);
    const fields: Partial<ContactFields> = {
      name: d.name.trim(), other_name: tidy(d.other_name), alias: tidy(d.alias), country: tidy(d.country), institution: tidy(d.institution),
      unit: tidy(d.unit), title: tidy(d.title), email: tidy(d.email), keywords: tidy(d.keywords), notes: tidy(d.notes),
      tags: [...new Set(d.tags.split(",").map((t) => t.trim()).filter(Boolean))],
    };
    let id = d.id;
    if (await act(d.id ? `Changed ${fields.name}` : `Added ${fields.name}`, async () => { id = await saveContact(d.id, fields); })) {
      draft = null;
      selected = id;
    }
  }
  function removePerson(c: Contact) {
    if (!confirm(`Delete ${c.name} and the ${metOf(c.id).length} times you met? (Undo brings them back.)`)) return;
    act(`Deleted ${c.name}`, () => remove("contact", c.id));
    selected = null;
    opened = false;
  }
  const addTag = (t: string) => {
    const now = draft!.tags.split(",").map((x) => x.trim()).filter(Boolean);
    if (!now.includes(t)) draft!.tags = [...now, t].join(", ");
  };

  // interactions
  let meet = $state({ met_on: today(), body: "" });
  let editingMeet = $state<{ id: string; met_on: string; body: string } | null>(null);
  async function addMeet(ev: SubmitEvent) {
    ev.preventDefault();
    if (!person || !meet.body.trim()) return;
    const f = { contact_id: person.id, met_on: meet.met_on || null, body: meet.body.trim() };
    if (await act(`Noted a meeting with ${person.name}`, () => saveInteraction(null, f))) meet = { met_on: today(), body: "" };
  }
  async function keepMeet() {
    const e = editingMeet!;
    if (!e.body.trim()) return;
    if (await act("Changed a note", () => saveInteraction(e.id, { met_on: e.met_on || null, body: e.body.trim() }))) editingMeet = null;
  }

  // ---- opportunities ------------------------------------------------------------------
  let showDone = $state(false);
  let opp = $state<{ id: string | null; name: string; deadline: string; notes: string } | null>(null);
  const opportunities = $derived(net.opportunities.filter((o) => showDone || !o.done)
    .sort((a, b) => Number(a.done) - Number(b.done) || (a.deadline ?? "9").localeCompare(b.deadline ?? "9")));
  const soon = (d: string | null) => !!d && d >= today() && d <= addDays(today(), 30);
  const late = (o: Opportunity) => !o.done && !!o.deadline && o.deadline < today();
  async function keepOpp(ev: SubmitEvent) {
    ev.preventDefault();
    const o = opp!;
    if (!o.name.trim()) return;
    if (await act(o.id ? "Changed opportunity" : "Added opportunity",
      () => saveOpportunity(o.id, { name: o.name.trim(), deadline: o.deadline || null, notes: o.notes.trim() || null }))) opp = null;
  }

  // ---- organisations ------------------------------------------------------------------
  let org = $state<{ id: string | null; name: string; notes: string } | null>(null);
  const peopleAt = (o: Organisation) => net.contacts.filter((c) => c.institution?.toLowerCase().includes(o.name.toLowerCase()));
  async function keepOrg(ev: SubmitEvent) {
    ev.preventDefault();
    const o = org!;
    if (!o.name.trim()) return;
    if (await act(o.id ? "Changed organisation" : "Added organisation", () => saveOrganisation(o.id, { name: o.name.trim(), notes: o.notes.trim() || null }))) org = null;
  }

  // ---- import ----------------------------------------------------------------------------
  let incoming = $state<ParsedNetwork | null>(null);
  let importing = $state(false);
  const isNew = (name: string) => !net.contacts.some((c) => c.name.trim().toLowerCase() === name.toLowerCase());
  async function readFile(ev: Event) {
    const input = ev.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    try {
      const p = parseNetwork(await readXlsx(await file.arrayBuffer()));
      if (!p.people.length && !p.opportunities.length && !p.organisations.length) error = `Nothing found in ${file.name}: a sheet of people needs a “Name” column.`;
      else incoming = p;
    } catch (e) {
      error = `Could not read ${file.name}: ${(e as Error).message}`;
    }
  }
  async function doImport() {
    const p = incoming!;
    importing = true;
    if (await act(`Imported ${p.people.length} people`, () => importNetwork(p, net))) incoming = null;
    importing = false;
  }

  // a note's [text](https://…) as a link
  const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
  const rich = (s: string) => escapeHtml(s).replace(/\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g, (_, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t || u}</a>`)
    .replace(/\n/g, "<br>");
</script>

<section class="network" class:opened>
  <div class="head">
    <div>
      <span class="eyebrow">Network</span>
      <h1>People you know</h1>
    </div>
    {#if !missing}
      <span class="head-acts">
        <label class="file-btn">Import .xlsx…<input type="file" accept=".xlsx" onchange={readFile} /></label>
        {#if view === "people"}<button class="primary" onclick={() => editPerson(null)}>+ Person</button>
        {:else if view === "opportunities"}<button class="primary" onclick={() => (opp = { id: null, name: "", deadline: "", notes: "" })}>+ Opportunity</button>
        {:else}<button class="primary" onclick={() => (org = { id: null, name: "", notes: "" })}>+ Organisation</button>{/if}
      </span>
    {/if}
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if missing}
    <p class="muted">Network needs its tables first: run <code>web/db/0062_network.sql</code> in the Supabase SQL editor, then reload.</p>
  {:else}
    {#if incoming}
      {@const fresh = incoming.people.filter((p) => isNew(p.name))}
      <div class="panel">
        <h2>Import</h2>
        <p class="small">
          <strong>{incoming.people.length} people</strong> ({fresh.length} new{incoming.people.length - fresh.length ? `, ${incoming.people.length - fresh.length} already here — they get any new tags and notes` : ""}),
          {incoming.people.reduce((a, p) => a + p.interactions.length, 0)} meetings
          ({incoming.people.reduce((a, p) => a + p.interactions.filter((i) => !i.met_on).length, 0)} without a date),
          {incoming.opportunities.length} opportunities, {incoming.organisations.length} organisations.
        </p>
        <p class="muted small">Tags from the sheets: {[...new Set(incoming.people.flatMap((p) => p.tags))].join(", ")}.
          {#if incoming.people.some((p) => p.tags.length > 1)}On more than one sheet, so one person with both tags: {incoming.people.filter((p) => p.tags.length > 1).map((p) => p.name).join(", ")}.{/if}</p>
        <div class="buttons">
          <button class="primary" disabled={importing} onclick={doImport}>{importing ? "Importing…" : "Import"}</button>
          <button onclick={() => (incoming = null)}>Cancel</button>
        </div>
      </div>
    {/if}

    <div class="views" role="tablist">
      <button role="tab" aria-selected={view === "people"} class:on={view === "people"} onclick={() => (view = "people")}>People <span>{net.contacts.length}</span></button>
      <button role="tab" aria-selected={view === "opportunities"} class:on={view === "opportunities"} onclick={() => (view = "opportunities")}>Opportunities <span>{net.opportunities.filter((o) => !o.done).length}</span></button>
      <button role="tab" aria-selected={view === "organisations"} class:on={view === "organisations"} onclick={() => (view = "organisations")}>Organisations <span>{net.organisations.length}</span></button>
    </div>

    {#if view === "people"}
      <div class="panes">
        <aside class="list">
          <input type="search" bind:value={query} placeholder="Search names, places, topics, notes…" aria-label="Search people" />
          {#if tags.length}
            <div class="chips" role="group" aria-label="Tag">
              <button class="chip" class:on={tag === null} onclick={() => (tag = null)}>All <span>{net.contacts.length}</span></button>
              {#each tags as [t, n] (t)}<button class="chip" class:on={tag === t} onclick={() => (tag = tag === t ? null : t)}>{t} <span>{n}</span></button>{/each}
            </div>
          {/if}
          <div class="status small"><span class="muted">{people.length} shown</span>
            <label>Sort <select bind:value={sort}><option value="az">A–Z</option><option value="met">Last met</option></select></label></div>
          <ul>
            {#each people as c (c.id)}
              {@const lm = lastMet(c.id)}
              <li>
                <button class:sel={c.id === selected} onclick={() => { selected = c.id; draft = null; editingMeet = null; opened = true; }}>
                  <span class="line"><span class="name">{c.name}</span>{#if c.alias}<span class="muted small">“{c.alias}”</span>{/if}</span>
                  <span class="muted small">{[c.institution, lm ? `met ${fmtDay(lm)}` : ""].filter(Boolean).join(" · ")}</span>
                </button>
              </li>
            {/each}
          </ul>
          {#if !net.contacts.length}<p class="muted small">No one yet. Import your spreadsheet, or add a person.</p>{/if}
        </aside>

        <div class="detail">
          <button class="back" onclick={() => { opened = false; draft = null; }}>← All people</button>
          {#if draft}
            <form class="panel" onsubmit={keepPerson}>
              <div class="grid">
                {#each FIELDS as [k, label, ph] (k)}
                  <label>{label}<input bind:value={draft[k] as string} placeholder={ph} required={k === "name"} /></label>
                {/each}
                <label class="full">Tags <span class="muted small">(comma between)</span><input bind:value={draft.tags} />
                  {#if tags.length}<span class="tag-picks">{#each tags as [t] (t)}<button type="button" class="link small" onclick={() => addTag(t)}>+ {t}</button>{/each}</span>{/if}
                </label>
                <label class="full">Notes <textarea rows="3" bind:value={draft.notes} placeholder="Anything else; links as [text](https://…)"></textarea></label>
              </div>
              <div class="buttons">
                <button class="primary" type="submit">{draft.id ? "Save" : "Add person"}</button>
                <button type="button" onclick={() => (draft = null)}>Cancel</button>
              </div>
            </form>
          {:else if person}
            <div class="p-head">
              <div>
                <h2>{person.name}{#if person.other_name}<span class="other"> {person.other_name}</span>{/if}</h2>
                <span class="muted">{[person.title, person.unit, person.institution, person.country].filter(Boolean).join(" · ")}</span>
              </div>
              <span class="tools">
                <button onclick={() => editPerson(person)}>Edit</button>
                <button class="del" onclick={() => removePerson(person)}>Delete</button>
              </span>
            </div>
            <dl>
              {#if person.alias}<dt>Goes by</dt><dd>{person.alias}</dd>{/if}
              {#if person.email}<dt>E-mail</dt><dd><a href={`mailto:${person.email}`}>{person.email}</a></dd>{/if}
              {#if person.keywords}<dt>Works on</dt><dd>{person.keywords}</dd>{/if}
              {#if person.tags.length}<dt>Tags</dt><dd>{#each person.tags as t (t)}<button class="chip small" onclick={() => { tag = t; opened = false; }}>{t}</button>{/each}</dd>{/if}
              {#if person.notes}<dt>Notes</dt><dd>{@html rich(person.notes)}</dd>{/if}
            </dl>

            <h3>Times you met</h3>
            <form class="add-meet" onsubmit={addMeet}>
              <input type="date" bind:value={meet.met_on} aria-label="When" />
              <input bind:value={meet.body} placeholder="Where, and what you talked about" aria-label="What about" />
              <button class="primary" type="submit">Add</button>
            </form>
            <ul class="meets">
              {#each metOf(person.id) as i (i.id)}
                <li>
                  {#if editingMeet?.id === i.id}
                    <form class="add-meet" onsubmit={(ev) => { ev.preventDefault(); keepMeet(); }}>
                      <input type="date" bind:value={editingMeet.met_on} aria-label="When" />
                      <input bind:value={editingMeet.body} aria-label="What about" />
                      <button class="primary" type="submit">Save</button>
                      <button type="button" onclick={() => (editingMeet = null)}>Cancel</button>
                      <button type="button" class="del" onclick={() => { editingMeet = null; act("Deleted a note", () => remove("contact_interaction", i.id)); }}>Delete</button>
                    </form>
                  {:else}
                    <button class="meet" title="Click to change or delete" onclick={() => (editingMeet = { id: i.id, met_on: i.met_on ?? "", body: i.body })}>
                      <span class="date">{i.met_on ? fmtDay(i.met_on) : "No date"}</span>
                      <span>{i.body}</span>
                    </button>
                  {/if}
                </li>
              {/each}
            </ul>
            {#if !metOf(person.id).length}<p class="muted small">Not noted yet.</p>{/if}
          {:else}
            <p class="muted">Pick someone on the left{net.contacts.length ? "" : ", or add a person"}.</p>
            {#if net.contacts.length}
              {@const recent = net.interactions.filter((i) => i.met_on).slice(0, 8)}
              {#if recent.length}
                <h3>Met lately</h3>
                <ul class="meets">
                  {#each recent as i (i.id)}
                    {@const c = net.contacts.find((x) => x.id === i.contact_id)}
                    <li><button class="meet" onclick={() => { selected = i.contact_id; opened = true; }}>
                      <span class="date">{fmtDay(i.met_on!)}</span><span><strong>{c?.name}</strong> — {i.body}</span>
                    </button></li>
                  {/each}
                </ul>
              {/if}
            {/if}
          {/if}
        </div>
      </div>
    {:else if view === "opportunities"}
      {#if opp}
        <form class="panel" onsubmit={keepOpp}>
          <div class="grid">
            <label class="wide">Scheme or call <input bind:value={opp.name} required /></label>
            <label>Deadline <input type="date" bind:value={opp.deadline} /></label>
            <label class="full">Notes <textarea rows="2" bind:value={opp.notes} placeholder="Who with, links as [text](https://…)"></textarea></label>
          </div>
          <div class="buttons">
            <button class="primary" type="submit">{opp.id ? "Save" : "Add"}</button>
            <button type="button" onclick={() => (opp = null)}>Cancel</button>
            {#if opp.id}{@const id = opp.id}<button type="button" class="del" onclick={() => { opp = null; act("Deleted opportunity", () => remove("opportunity", id)); }}>Delete</button>{/if}
          </div>
        </form>
      {/if}
      <label class="small show-done"><input type="checkbox" bind:checked={showDone} /> Show done</label>
      <table>
        <thead><tr><th>Done</th><th>Scheme or call</th><th>Deadline</th><th>Notes</th><th></th></tr></thead>
        <tbody>
          {#each opportunities as o (o.id)}
            <tr class:done={o.done}>
              <td><input type="checkbox" checked={o.done} aria-label={`Done: ${o.name}`}
                         onchange={(ev) => act(ev.currentTarget.checked ? "Marked opportunity done" : "Reopened opportunity", () => saveOpportunity(o.id, { done: !o.done }))} /></td>
              <td>{o.name}</td>
              <td class="nowrap" class:late={late(o)}>{o.deadline ? fmtDay(o.deadline) : "—"}{late(o) ? " ⚠ passed" : soon(o.deadline) && !o.done ? " · soon" : ""}</td>
              <td class="small">{#if o.notes}{@html rich(o.notes)}{/if}</td>
              <td class="row-acts"><button class="mini" onclick={() => (opp = { id: o.id, name: o.name, deadline: o.deadline ?? "", notes: o.notes ?? "" })}>Edit</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if !opportunities.length}<p class="muted small">No opportunities{showDone ? "" : " open"}.</p>{/if}
    {:else}
      {#if org}
        <form class="panel" onsubmit={keepOrg}>
          <div class="grid">
            <label class="wide">Name <input bind:value={org.name} required /></label>
            <label class="full">Notes <textarea rows="2" bind:value={org.notes}></textarea></label>
          </div>
          <div class="buttons">
            <button class="primary" type="submit">{org.id ? "Save" : "Add"}</button>
            <button type="button" onclick={() => (org = null)}>Cancel</button>
            {#if org.id}{@const id = org.id}<button type="button" class="del" onclick={() => { org = null; act("Deleted organisation", () => remove("organisation", id)); }}>Delete</button>{/if}
          </div>
        </form>
      {/if}
      <table>
        <thead><tr><th>Organisation</th><th>Notes</th><th>People there</th><th></th></tr></thead>
        <tbody>
          {#each net.organisations as o (o.id)}
            <tr>
              <td>{o.name}</td>
              <td class="small">{#if o.notes}{@html rich(o.notes)}{/if}</td>
              <td class="small">{#each peopleAt(o) as c, i (c.id)}{i ? ", " : ""}<button class="link" onclick={() => { view = "people"; selected = c.id; opened = true; }}>{c.name}</button>{/each}</td>
              <td class="row-acts"><button class="mini" onclick={() => (org = { id: o.id, name: o.name, notes: o.notes ?? "" })}>Edit</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if !net.organisations.length}<p class="muted small">No organisations yet.</p>{/if}
      <p class="muted small">People are listed under an organisation when its name is in their institution.</p>
    {/if}
  {/if}
</section>

<style>
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .head h1 { margin: 0; }
  .head-acts { display: flex; gap: 0.5rem; align-items: center; }
  .file-btn { border: 1px solid var(--rule); background: var(--panel); border-radius: var(--radius); padding: 0.45rem 0.9rem; cursor: pointer; font-family: var(--font-ui); font-size: 0.9rem; }
  .file-btn input { display: none; }
  .small { font-size: 0.8rem; }
  .nowrap { white-space: nowrap; }
  .link { background: none; border: none; padding: 0; color: var(--accent); cursor: pointer; font: inherit; }
  .panel { background: var(--panel); border-radius: var(--radius); padding: 0.9rem; display: grid; gap: 0.6rem; margin-bottom: 1rem; }
  .panel h2 { margin: 0; font-size: 1.1rem; }
  .panel p { margin: 0; }
  .panel label { display: grid; gap: 0.25rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem; }
  .grid .wide { grid-column: span 2; }
  .grid .full { grid-column: 1 / -1; }
  .tag-picks { display: flex; flex-wrap: wrap; gap: 0.6rem; }
  .buttons { display: flex; gap: 0.5rem; }
  .views { display: flex; gap: 0.25rem; margin-bottom: 1rem; font-family: var(--font-ui); border-bottom: 1px solid var(--rule); }
  .views button { background: none; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 0.45rem 0.8rem; color: var(--ink-soft); }
  .views button.on { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
  .views span { color: var(--ink-soft); font-weight: 400; margin-left: 0.2rem; }

  .panes { display: grid; grid-template-columns: minmax(0, 19rem) minmax(0, 1fr); gap: 1.5rem; align-items: start; }
  .list { position: sticky; top: 4rem; display: grid; gap: 0.5rem; font-family: var(--font-ui); max-height: calc(100vh - 5rem); }
  .list ul { list-style: none; margin: 0; padding: 0; overflow-y: auto; min-height: 0; }
  .list li button { width: 100%; display: grid; gap: 0.05rem; text-align: left; background: none; border: none; border-radius: var(--radius); padding: 0.4rem 0.55rem; }
  .list li button:hover { background: var(--panel); }
  .list li button.sel { background: var(--panel); box-shadow: inset 3px 0 0 var(--accent); }
  .line { display: flex; gap: 0.4rem; align-items: baseline; }
  .name { font-weight: 600; font-size: 0.9rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .chip { font-size: 0.78rem; padding: 0.12rem 0.6rem; border-radius: 999px; background: none; font-family: var(--font-ui); margin-right: 0.25rem; }
  .chip span { color: var(--ink-soft); }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .chip.on span { color: inherit; opacity: 0.8; }
  .status { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--rule); padding-bottom: 0.3rem; }
  .status label { display: flex; gap: 0.3rem; align-items: center; color: var(--ink-soft); }
  .status select { width: auto; padding: 0.1rem 0.3rem; font-size: 0.8rem; }
  .back { display: none; margin-bottom: 0.8rem; }

  .p-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 0.6rem; }
  .p-head h2 { margin: 0; }
  .other { font-weight: 400; color: var(--ink-soft); }
  .tools { display: flex; gap: 0.3rem; }
  .tools button { font-size: 0.82rem; padding: 0.3rem 0.7rem; }
  .del { color: var(--danger); }
  dl { display: grid; grid-template-columns: 7rem minmax(0, 1fr); gap: 0.35rem 0.8rem; margin: 1rem 0; }
  dt { font-family: var(--font-ui); font-size: 0.8rem; color: var(--ink-soft); }
  dd { margin: 0; overflow-wrap: anywhere; }
  h3 { font-size: 1rem; margin: 1.2rem 0 0.5rem; }
  .add-meet { display: grid; grid-template-columns: 9.5rem minmax(0, 1fr) auto auto auto; gap: 0.35rem; margin-bottom: 0.5rem; }
  .add-meet button { font-size: 0.82rem; padding: 0.3rem 0.7rem; }
  .meets { list-style: none; margin: 0; padding: 0; }
  .meets li { border-bottom: 1px solid var(--rule); }
  .meet { width: 100%; display: grid; grid-template-columns: 7.5rem minmax(0, 1fr); gap: 0.6rem; text-align: left; background: none; border: none; border-radius: 0; padding: 0.45rem 0.2rem; font-size: 0.92rem; }
  .meet:hover { background: var(--panel); }
  .meet .date { font-family: var(--font-ui); font-size: 0.8rem; color: var(--ink-soft); }

  .show-done { display: flex; gap: 0.3rem; align-items: center; font-family: var(--font-ui); color: var(--ink-soft); margin-bottom: 0.4rem; }
  .show-done input { width: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th { text-align: left; font-family: var(--font-ui); font-size: 0.75rem; font-weight: 600; color: var(--ink-soft); padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--rule); }
  td { padding: 0.4rem; border-bottom: 1px solid var(--rule); vertical-align: top; }
  td input[type="checkbox"] { width: auto; }
  tr.done td { color: var(--ink-soft); text-decoration: line-through; }
  .late { color: var(--danger); }
  .row-acts { text-align: right; white-space: nowrap; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.5rem; }

  @media (max-width: 48rem) {
    .panes { grid-template-columns: 1fr; }
    .list { position: static; max-height: none; }
    .network.opened .list, .network:not(.opened) .detail { display: none; }
    .back { display: inline-block; }
    .grid { grid-template-columns: 1fr 1fr; }
    .add-meet { grid-template-columns: 1fr 1fr; }
    .add-meet input:nth-child(2) { grid-column: 1 / -1; grid-row: 2; }
    dl { grid-template-columns: 1fr; gap: 0.1rem; }
  }
</style>
