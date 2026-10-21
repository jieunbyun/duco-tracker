<script lang="ts">
  import { untrack } from "svelte";
  import {
    LANES, NODE_KINDS, GRANT_STAGES, staged, setContributors, fromMonth, saveNode, deleteNode, saveLink, deleteLink, loadRevisions, addRevision,
  } from "./pathways";
  import type { PwNode, PwNodeFields, PwLink, PwRevision, NodeKind, Lane, GrantStage } from "./pathways";
  import type { Project } from "./data";
  import { setProjectDates } from "./data";
  import type { Reading } from "./reading";
  import type { GroupProject, Member } from "./group";
  import { LIVE_STATUSES } from "./plan";
  import { fmtDay } from "./dates";

  type Props = {
    node: PwNode | null; // null = new
    draft?: Partial<PwNodeFields>; // defaults for a new item
    nodes: PwNode[];
    links: PwLink[];
    projects: Project[];
    readings: Reading[];
    groupProjects?: GroupProject[]; // members' shared projects (Members tab)
    members?: Member[]; // the group, to name contributors
    contributors?: string[]; // this item's contributors now
    onsaved: () => void;
    oncancel: () => void;
  };
  let { node, draft, nodes, links, projects, readings, groupProjects = [], members = [], contributors = [], onsaved, oncancel }: Props = $props();
  const had = untrack(() => contributors);
  let contrib = $state<string[]>([...untrack(() => contributors)]);
  const eligible = $derived(members.filter((m) => m.active || contrib.includes(m.user_id)));

  const n0 = untrack(() => node);
  const d0 = untrack(() => draft) ?? {};
  let f = $state({
    kind: (n0?.kind ?? d0.kind ?? "project") as NodeKind,
    lane: (n0?.lane ?? d0.lane ?? "goals") as Lane,
    title: n0?.title ?? "",
    detail: n0?.detail ?? "",
    status: n0?.status ?? "active",
    potential: n0?.potential ?? d0.potential ?? false,
    project_id: n0?.project_id ?? "",
    reading_id: n0?.reading_id ?? "",
    start_on: (n0?.start_on ?? d0.start_on ?? "").slice(0, 7), // months, as "YYYY-MM"
    end_on: (n0?.end_on ?? d0.end_on ?? "").slice(0, 7),
    effort_pm: n0?.effort_pm ?? (null as number | null),
    cost: n0?.cost ?? (null as number | null),
    fte: n0?.fte ?? (null as number | null),
    grant_stage: (n0?.grant_stage ?? d0.grant_stage ?? "drafting") as GrantStage,
    hands_on: n0?.hands_on ?? false,
    show_milestones: n0?.show_milestones ?? false,
    group_project_id: n0?.group_project_id ?? "",
    folder_url: n0?.folder_url ?? "",
  });
  // projects and grants can each be a Planning project (a grant: one under Proposals)
  const plannable = $derived(f.kind === "project" || f.kind === "grant");
  // a linked Planning project lends its current name and dates
  {
    const p = n0?.project_id ? untrack(() => projects).find((x) => x.id === n0.project_id) : undefined;
    if (p) {
      f.title = p.name;
      f.start_on = p.start_on?.slice(0, 7) ?? f.start_on;
      f.end_on = p.end_on?.slice(0, 7) ?? f.end_on;
    }
  }
  // the exact dates behind the months shown, kept when a month is left as it is
  const wasStart = untrack(() => projects).find((x) => x.id === n0?.project_id)?.start_on ?? n0?.start_on ?? null;
  const wasEnd = untrack(() => projects).find((x) => x.id === n0?.project_id)?.end_on ?? n0?.end_on ?? null;
  const linkedProject = $derived(plannable && f.project_id ? projects.find((x) => x.id === f.project_id) ?? null : null);
  let reason = $state("");
  let busy = $state(false);
  let error = $state("");
  let revisions = $state<PwRevision[]>([]);
  if (n0?.kind === "goal") loadRevisions(n0.id).then((r) => (revisions = r)).catch(() => {});

  const dated = true; // goals too: without dates a goal sits in the goals column
  const reworded = $derived(!!n0 && n0.kind === "goal" && (f.title.trim() !== n0.title || (f.detail.trim() || null) !== n0.detail));
  const projectOptions = $derived(
    projects.filter((p) => LIVE_STATUSES.has(p.status) || p.id === n0?.project_id).sort((a, b) => a.name.localeCompare(b.name)),
  );
  const title = (id: string) => nodes.find((x) => x.id === id)?.title ?? "?";
  const mine = $derived(n0 ? links.filter((l) => l.from_id === n0.id || l.to_id === n0.id) : []);

  // a linked Planning project lends its dates when they are empty
  // linking a Planning project takes its name and dates (and keeps them in step from then on)
  function onProject() {
    const p = projects.find((x) => x.id === f.project_id);
    if (!p) return;
    f.title = p.name;
    if (p.start_on) f.start_on = p.start_on.slice(0, 7);
    if (p.end_on) f.end_on = p.end_on.slice(0, 7);
    f.potential = false;
  }

  const n = (v: number | null) => (v === null || Number.isNaN(v) ? null : v);
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!f.title.trim()) return (error = "Give it a title.");
    if (f.start_on && f.end_on && f.end_on < f.start_on) return (error = "It ends before it starts.");
    busy = true;
    error = "";
    const p = linkedProject;
    const startOn = fromMonth(f.start_on, false, p ? p.start_on : wasStart);
    const endOn = fromMonth(f.end_on, true, p ? p.end_on : wasEnd);
    try {
      const fields: Partial<PwNodeFields> = {
        kind: f.kind, lane: f.lane, title: f.title.trim(), detail: f.detail.trim() || null, status: f.status as PwNode["status"],
        potential: f.kind === "project" ? f.potential : false,
        project_id: plannable ? f.project_id || null : null,
        reading_id: f.kind === "gap" ? f.reading_id || null : null,
        start_on: dated ? startOn : null, end_on: dated ? endOn : null,
        effort_pm: f.kind === "project" ? n(f.effort_pm) : null,
        cost: plannable ? n(f.cost) : null,
        fte: f.kind === "person" ? n(f.fte) : null,
        grant_stage: staged(f.kind) ? f.grant_stage : null,
        hands_on: f.kind === "project" ? f.hands_on : false,
        show_milestones: plannable && !!f.project_id ? f.show_milestones : false,
        folder_url: f.folder_url.trim() || null,
        ...(groupProjects.length || n0?.group_project_id ? { group_project_id: f.kind === "project" ? f.group_project_id || null : null } : {}),
      };
      if (!n0) Object.assign(fields, { lane_row: d0.lane_row ?? 0 });
      if (reworded && n0) await addRevision(n0.id, n0.title, n0.detail, reason.trim() || null);
      // a linked project keeps the Planning project's dates in step
      if (p && (startOn !== p.start_on || endOn !== p.end_on)) {
        await setProjectDates(p.id, startOn, endOn);
      }
      const id = await saveNode(n0?.id ?? null, fields);
      if (members.length) await setContributors(id, contrib, had);
      onsaved();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!n0 || !confirm(`Delete “${n0.title}” and its links?`)) return;
    busy = true;
    try {
      await deleteNode(n0.id);
      onsaved();
    } catch (e) {
      error = (e as Error).message;
      busy = false;
    }
  }

  // ---- links ----------------------------------------------------------------------
  let linkTo = $state("");
  async function addLink() {
    if (!n0 || !linkTo) return;
    try {
      await saveLink(n0.id, linkTo);
      linkTo = "";
      onsaved();
    } catch (e) {
      error = (e as Error).message;
    }
  }
  async function unlink(l: PwLink) {
    try { await deleteLink(l.id); onsaved(); } catch (e) { error = (e as Error).message; }
  }
</script>

<form class="pw-form" onsubmit={save}>
  <label>Kind
    <select bind:value={f.kind} disabled={!!n0}>
      {#each NODE_KINDS as k (k.key)}<option value={k.key}>{k.label}</option>{/each}
    </select>
  </label>
  <label>Lane
    <select bind:value={f.lane}>{#each LANES as l (l.key)}<option value={l.key}>{l.label}</option>{/each}</select>
  </label>
  <label>Status
    <select bind:value={f.status}>
      <option value="active">active</option><option value="done">done</option><option value="retired">retired</option>
    </select>
  </label>

  <label class="wide">{f.kind === "person" ? "Name and role" : "Title"}
    <input bind:value={f.title} required readonly={!!linkedProject} />
    {#if linkedProject}<span class="synced">Named in Planning; its dates here and in Planning stay in step.</span>{/if}
  </label>
  <label class="wide">OneDrive folder (link)
    <input type="url" bind:value={f.folder_url} placeholder={linkedProject?.folder_url ? "the Planning project's folder" : "https://…sharepoint.com/…"} />
  </label>
  <label class="wide">{f.kind === "person" ? "Original strengths, and the legacy they will leave" : "Description"}
    <textarea rows="3" bind:value={f.detail}></textarea>
  </label>

  {#if reworded}
    <label class="wide reason">Why the change? (kept in the goal's history)
      <input bind:value={reason} placeholder="e.g. narrowed after the funding call" />
    </label>
  {/if}

  {#if f.kind === "project"}
    <label class="wide">Planning project (if it exists)
      <select bind:value={f.project_id} onchange={onProject}>
        <option value="">— none: a potential project —</option>
        {#each projectOptions as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
      </select>
    </label>
    <label class="check wide"><input type="checkbox" bind:checked={f.hands_on} /> Hands-on — my own research time goes into it substantially</label>
    {#if f.project_id}
      <label class="check wide"><input type="checkbox" bind:checked={f.show_milestones} />
        Show its milestones on the map ({linkedProject?.milestone.length ?? 0}, from Planning)</label>
    {/if}
    {#if groupProjects.length}
      <label class="wide">A member's project (Members tab)
        <select bind:value={f.group_project_id}>
          <option value="">— none —</option>
          {#each groupProjects as g (g.id)}<option value={g.id}>{g.title}</option>{/each}
        </select>
      </label>
    {/if}
    {#if !f.project_id}
      <label class="check"><input type="checkbox" bind:checked={f.potential} /> Potential (not started)</label>
    {/if}
    <label>Effort (person-months) <input type="number" min="0" step="0.5" bind:value={f.effort_pm} /></label>
    <label>Cost <input type="number" min="0" step="100" bind:value={f.cost} /></label>
  {/if}
  {#if f.kind === "grant"}
    <label class="wide">Planning project (if you track the writing there)
      <select bind:value={f.project_id} onchange={onProject}>
        <option value="">— none —</option>
        {#each projectOptions as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
      </select>
    </label>
    <label>Stage
      <select bind:value={f.grant_stage}>{#each GRANT_STAGES as s (s)}<option value={s}>{s}</option>{/each}</select>
    </label>
    <label>Amount sought (optional) <input type="number" min="0" step="1000" bind:value={f.cost} /></label>
    <p class="hint wide">Link it to what it would fund — projects, people, objectives. They read “funding pending” until it is awarded.</p>
  {/if}
  {#if f.kind === "award"}
    <label>Stage
      <select bind:value={f.grant_stage}>{#each GRANT_STAGES as s (s)}<option value={s}>{s}</option>{/each}</select>
    </label>
  {/if}
  {#if f.kind === "person"}
    <label>Share of time (0–1) <input type="number" min="0" max="1" step="0.05" bind:value={f.fte} /></label>
  {/if}
  {#if f.kind === "gap"}
    <label class="wide">Reading on it
      <select bind:value={f.reading_id}>
        <option value="">— none —</option>
        {#each readings as r (r.id)}<option value={r.id}>{r.title}</option>{/each}
      </select>
    </label>
  {/if}
  {#if dated}
    <label>{staged(f.kind) ? "Writing from" : f.kind === "goal" ? "From (optional)" : "From"} <input type="month" bind:value={f.start_on} /></label>
    <label>{staged(f.kind) ? "Deadline" : f.kind === "goal" ? "By (optional)" : "To"} <input type="month" bind:value={f.end_on} min={f.start_on || undefined} /></label>
    {#if f.kind === "goal"}
      <p class="hint wide">Without dates the goal sits in the goals column at the horizon; with them it sits on the timeline. You can also drag it between the two.</p>
    {/if}
  {/if}

  {#if eligible.length && f.kind !== "goal"}
    <fieldset class="wide contrib">
      <legend>Contributors — they see this item, and the goals it leads to, on their own chart</legend>
      {#each eligible as m (m.user_id)}
        <label class="check"><input type="checkbox" value={m.user_id} bind:group={contrib} /> {m.role === "supervisor" ? `${m.display_name} (you)` : m.display_name}</label>
      {/each}
    </fieldset>
  {/if}

  {#if n0}
    <div class="wide links">
      <h3>Links</h3>
      {#each mine as l (l.id)}
        <div class="link-row">
          {#if l.from_id === n0.id}
            <span class="muted">this →</span> <strong>{title(l.to_id)}</strong>
          {:else}
            <strong>{title(l.from_id)}</strong> <span class="muted">→ this</span>
          {/if}
          <button type="button" class="mini danger" aria-label="Remove link" onclick={() => unlink(l)}>✕</button>
        </div>
      {:else}
        <p class="muted small">No links yet — drag from an item's ○ to another, or add one here.</p>
      {/each}
      <div class="link-add">
        <span class="muted">this →</span>
        <select bind:value={linkTo} aria-label="Link to">
          <option value="">choose an item…</option>
          {#each LANES as lane (lane.key)}
            <optgroup label={lane.label}>
              {#each nodes.filter((x) => x.lane === lane.key && x.id !== n0.id) as x (x.id)}<option value={x.id}>{x.title}</option>{/each}
            </optgroup>
          {/each}
        </select>
        <button type="button" class="mini" disabled={!linkTo} onclick={addLink}>Link</button>
      </div>
    </div>
  {/if}

  {#if revisions.length}
    <details class="wide history">
      <summary class="muted">Earlier wording ({revisions.length})</summary>
      {#each revisions as r (r.id)}
        <div class="rev">
          <span class="muted small">until {fmtDay(r.changed_at.slice(0, 10))}{r.reason ? ` — ${r.reason}` : ""}</span>
          <p>{r.old_title}{r.old_detail ? ` — ${r.old_detail}` : ""}</p>
        </div>
      {/each}
    </details>
  {/if}

  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{n0 ? "Save" : "Add"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if n0}<button type="button" class="danger push" onclick={remove} disabled={busy}>Delete</button>{/if}
  </div>
</form>

<style>
  .pw-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.65rem 1rem; font-family: var(--font-ui); }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .check { display: flex; align-items: center; gap: 0.45rem; align-self: end; padding-bottom: 0.5rem; color: var(--ink); }
  .check input { width: auto; }
  .reason { color: var(--accent); }
  .synced { font-size: 0.75rem; color: var(--accent); }
  .contrib { display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.4rem 0.7rem; }
  .contrib legend { font-size: 0.8rem; color: var(--ink-soft); padding: 0 0.3rem; }
  .hint { font-size: 0.78rem; color: var(--ink-soft); margin: -0.3rem 0 0; }
  .links h3 { font-size: 0.9rem; margin: 0 0 0.3rem; }
  .link-row, .link-add { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; font-size: 0.85rem; padding: 0.15rem 0; }
  .link-add select { width: auto; font-size: 0.8rem; padding: 0.2rem 0.3rem; }
  .link-add { margin-top: 0.3rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.5rem; }
  .small { font-size: 0.8rem; margin: 0; }
  .history summary { cursor: pointer; font-size: 0.85rem; }
  .rev p { margin: 0.1rem 0 0.4rem; font-size: 0.88rem; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { color: var(--danger); }
  .push { margin-left: auto; }
  @media (max-width: 40rem) { .pw-form { grid-template-columns: 1fr; } }
</style>
