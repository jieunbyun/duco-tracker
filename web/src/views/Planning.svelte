<script lang="ts">
  import FolderLink from "../lib/FolderLink.svelte";
  import ExportData from "../lib/ExportData.svelte";
  import { undoable, undoLast } from "../lib/undo.svelte";
  import { loadTaxonomy, loadProjects, loadAllHours, targetOn, fmtHours, setProjectStatus } from "../lib/data";
  import type { Taxonomy, Project, HourRow, Category } from "../lib/data";
  import { horizonRange, projectLoad, areaHorizons, plannedOf, PLANNABLE_KINDS, PACE_DAYS } from "../lib/horizon";
  import type { ProjectLoad } from "../lib/horizon";
  import { fmtDay, today, addDays } from "../lib/dates";
  import ProjectEditor from "../lib/ProjectEditor.svelte";
  import Milestones from "../lib/Milestones.svelte";
  import Settings from "../lib/Settings.svelte";
  import CategoryNotes from "../lib/CategoryNotes.svelte";
  import { shareEmail } from "../lib/email";
  import { loadGroupProjects, loadMilestones as loadSharedMilestones } from "../lib/group";
  import type { GroupProject } from "../lib/group";

  let tax = $state<Taxonomy | null>(null);
  let projects = $state<Project[]>([]);
  let hours = $state<HourRow[]>([]);
  let groupProjects = $state<GroupProject[]>([]); // shared projects a Planning project can stand for
  let privateShared = $state(new Map<string, boolean>()); // their milestones: private (only you) or public
  let loading = $state(true);
  let error = $state("");

  async function load() {
    try {
      const [t, p, h, g, gm] = await Promise.all([
        loadTaxonomy(), loadProjects(), loadAllHours(), loadGroupProjects(true).catch(() => [] as GroupProject[]),
        loadSharedMilestones().catch(() => []),
      ]);
      privateShared = new Map(gm.map((m) => [m.id, m.is_private]));
      tax = t;
      projects = p;
      hours = h;
      groupProjects = g;
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  // ---- derived figures ----------------------------------------------------
  // The viewing period: a button choice remembered in this browser, else the
  // months in your settings.
  type Horizon = { key: string; label: string; title: string; weeks?: number; months?: number };
  const HORIZONS: Horizon[] = [
    { key: "2w", label: "2 wk", title: "next 2 weeks", weeks: 2 },
    { key: "1m", label: "1 mo", title: "next month", months: 1 },
    ...[3, 6, 12, 18, 24].map((m) => ({ key: `${m}m`, label: `${m} mo`, title: `next ${m} months`, months: m })),
  ];
  const HORIZON_KEY = "planning.horizon";
  function savedHorizon(): string | null {
    try { return localStorage.getItem(HORIZON_KEY); } catch { return null; }
  }
  let horizonKey = $state<string | null>(savedHorizon());
  const choice = $derived.by((): Horizon => {
    const found = HORIZONS.find((h) => h.key === horizonKey);
    if (found) return found;
    const m = tax?.horizonMonths ?? 12;
    return HORIZONS.find((h) => h.key === `${m}m`) ?? { key: `${m}m`, label: `${m} mo`, title: `next ${m} months`, months: m };
  });
  const horizon = $derived(
    choice.weeks ? { from: today(), to: addDays(today(), 7 * choice.weeks - 1) } : horizonRange(choice.months ?? 12),
  );
  function setHorizon(key: string) {
    horizonKey = key;
    try { localStorage.setItem(HORIZON_KEY, key); } catch {}
  }

  const actualByProject = $derived.by(() => {
    const m = new Map<string, number>();
    for (const h of hours) if (h.project_id) m.set(h.project_id, (m.get(h.project_id) ?? 0) + h.hours);
    return m;
  });
  const actualByMilestone = $derived.by(() => {
    const m = new Map<string, number>();
    for (const h of hours) if (h.milestone_id) m.set(h.milestone_id, (m.get(h.milestone_id) ?? 0) + h.hours);
    return m;
  });
  const loads = $derived(
    new Map(projects.map((p) => [p.id, projectLoad(p, actualByProject.get(p.id) ?? 0, horizon, actualByMilestone)] as const)),
  );
  // Routine time counts email in equal shares to each area with an Email category.
  const areaRows = $derived(tax ? areaHorizons(tax, shareEmail(hours, tax), projects, loads, horizon) : []);
  // Teaching and Admin also shown together: their capacity, routine and
  // projects added up, the projects stacked in each area's colour.
  const COMBINED = ["TEA", "ADM"];
  const combo = $derived.by(() => {
    const parts = COMBINED.map((code) => areaRows.find((r) => r.area.code === code)).filter((r) => !!r);
    if (parts.length < 2) return null;
    const sum = (k: "capacity" | "routine" | "committed" | "free" | "freePerWeek") => parts.reduce((s, r) => s + r![k], 0);
    return {
      parts,
      label: parts.map((r) => r!.area.label).join(" + "),
      capacity: sum("capacity"), routine: sum("routine"), committed: sum("committed"),
      free: sum("free"), freePerWeek: sum("freePerWeek"),
    };
  });
  const scale = $derived(Math.max(1, ...areaRows.map((r) => Math.max(r.capacity, r.routine + r.committed)),
    combo ? Math.max(combo.capacity, combo.routine + combo.committed) : 0));
  const total = $derived(
    areaRows.reduce(
      (s, r) => ({ capacity: s.capacity + r.capacity, routine: s.routine + r.routine,
                   committed: s.committed + r.committed, free: s.free + r.free }),
      { capacity: 0, routine: 0, committed: 0, free: 0 },
    ),
  );

  const areaIndex = $derived(new Map((tax?.areas ?? []).map((a, i) => [a.id, i])));
  function areaColor(areaId: string): string {
    const i = areaIndex.get(areaId) ?? 99;
    return i < 4 ? `var(--series-${i + 1})` : "var(--ink-soft)";
  }

  // ---- project list ---------------------------------------------------------
  let showFinished = $state(false);

  // ---- tick a project complete, with a moment to undo (the app's undo) -------------------
  let flash = $state<{ text: string; undo?: boolean } | null>(null);
  let flashTimer: ReturnType<typeof setTimeout> | undefined;
  function showFlash(text: string, undo?: boolean) {
    flash = { text, undo };
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => (flash = null), 8000);
  }
  async function setComplete(p: Project, done: boolean) {
    const label = done ? `Marked “${p.name}” done` : `Reopened “${p.name}”`;
    try {
      await undoable(label, () => setProjectStatus(p.id, done ? "done" : "active"));
      showFlash(done && !showFinished ? `${label} — hidden with done projects` : label, true);
    } catch (e) {
      error = (e as Error).message;
    }
    await load();
  }
  let editingSettings = $state(false);
  async function settingsSaved() {
    editingSettings = false;
    await load();
  }
  let expanded = $state<string | null>(null);
  let addingTo = $state<string | null>(null); // category id

  const visible = $derived(projects.filter((p) => showFinished || !["done", "dropped"].includes(p.status)));
  const editorCategories = $derived(
    (tax?.categories ?? []).map((c) => ({
      category: c,
      areaLabel: tax!.areas.find((a) => a.id === c.area_id)?.label ?? "",
    })),
  );

  function projectsIn(c: Category): Project[] {
    return visible
      .filter((p) => p.category_id === c.id)
      .sort((a, b) => Number(b.is_important) - Number(a.is_important) || (a.end_on ?? "9").localeCompare(b.end_on ?? "9"));
  }

  function toggle(id: string) {
    expanded = expanded === id ? null : id;
    addingTo = null;
  }
  function startAdding(categoryId: string) {
    addingTo = categoryId;
    expanded = null;
  }
  // one in the bin stays listed while it is linked: saving must not unlink it
  const sharedChoices = $derived(groupProjects.map((g) => ({
    id: g.id, title: g.title, taken: projects.some((p) => p.group_project_id === g.id), binned: !!g.deleted_at,
  })).filter((g) => g.taken || !g.binned));
  const sharedTitle = (p: Project) => groupProjects.find((g) => g.id === p.group_project_id)?.title ?? "";

  async function changed() {
    addingTo = null;
    await load();
  }

  function flagText(l: ProjectLoad, p: Project): string {
    switch (l.flag) {
      case "no-plan": return "no planned hours";
      case "no-end": return "no end date — all remaining hours counted now";
      case "overdue": return `past end date · ${fmtHours(l.remaining)} left`;
      case "over-budget": return `over plan by ${fmtHours(l.overBy)}`;
      default: return l.perWeek ? `needs ${fmtHours(l.perWeek)}/wk to finish` : "";
    }
  }
  const warn = (l: ProjectLoad) => l.flag === "overdue" || l.flag === "over-budget";

  /** " (38%)": part of capacity, or nothing when there is no capacity to compare with. */
  function share(part: number, capacity: number, suffix = ""): string {
    return capacity > 0 ? ` (${Math.round((100 * part) / capacity)}%${suffix})` : "";
  }

  function period(p: Project): string {
    if (!p.start_on && !p.end_on) return "no dates";
    return `${p.start_on ? fmtDay(p.start_on) : "…"} – ${p.end_on ? fmtDay(p.end_on) : "…"}`;
  }
</script>

<section class="planning">
  <span class="eyebrow">Planning</span>
  <h1>Planning</h1>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if tax}
    <!-- ================= horizon ================= -->
    {#snippet breakdown(projs: { id: string; name: string; hours: number }[], routine: { id: string; label: string; hours: number }[])}
      <!-- shown on hover (or when the row has focus): what the hours are made of -->
      <div class="breakdown" role="tooltip">
        <div>
          <strong>Committed to projects</strong>
          {#each projs as x (x.id)}<span><span>{x.name}</span><span>{fmtHours(x.hours)}</span></span>{:else}<span class="muted">none</span>{/each}
        </div>
        <div>
          <strong>Routine (projected)</strong>
          {#each routine as x (x.id)}<span><span>{x.label}</span><span>{fmtHours(x.hours)}</span></span>{:else}<span class="muted">none</span>{/each}
        </div>
      </div>
    {/snippet}
    <div class="horizon-head">
      <h2>Remaining time · {choice.title}</h2>
      <div class="horizon-pick" role="group" aria-label="Viewing period">
        {#each HORIZONS as h (h.key)}
          <button class:on={choice.key === h.key} aria-pressed={choice.key === h.key}
                  onclick={() => setHorizon(h.key)}>{h.label}</button>
        {/each}
      </div>
    </div>
    <p class="muted note">
      {fmtDay(horizon.from)} – {fmtDay(horizon.to)}. Routine time is projected at your pace over the last
      {PACE_DAYS / 7} weeks; projects count their remaining planned hours, spread to their end date.
    </p>
    <div class="legend" aria-hidden="true">
      <span><i class="sw routine"></i>Routine (projected)</span>
      <span><i class="sw committed"></i>Committed to projects</span>
      <span><i class="sw free"></i>Free</span>
      <span><i class="sw cap"></i>Capacity</span>
    </div>

    <div class="horizon">
      {#each areaRows as r (r.area.id)}
        {@const over = r.free < 0}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div class="h-row" tabindex="0">
          <span class="name">{r.area.label}</span>
          <div class="stack" aria-hidden="true">
            <span class="seg routine" style:width={`${(100 * r.routine) / scale}%`}></span>
            <span class="seg committed" style:width={`${(100 * r.committed) / scale}%`} style:background={areaColor(r.area.id)}></span>
            {#if !over}<span class="seg free" style:width={`${(100 * r.free) / scale}%`}></span>{/if}
            <span class="cap" style:left={`${(100 * r.capacity) / scale}%`}></span>
          </div>
          <span class="value" class:over>
            {#if over}
              <strong>⚠ over by {fmtHours(-r.free)}{share(-r.free, r.capacity, " over")}</strong>
            {:else}
              <strong>{fmtHours(r.free)} free{share(r.free, r.capacity)}</strong>
              <span class="muted">· ≈ {fmtHours(r.freePerWeek)}/wk</span>
            {/if}
          </span>
          <span class="detail muted">
            capacity {fmtHours(r.capacity)} · routine {fmtHours(r.routine)} · projects {fmtHours(r.committed)}
          </span>
          {@render breakdown(r.committedBy, r.routineBy)}
        </div>
      {/each}
      {#if combo}
        {@const over = combo.free < 0}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div class="h-row combo" tabindex="0">
          <span class="name"><em>{combo.label}</em> <small class="tag">combined</small></span>
          <div class="stack thin" aria-hidden="true">
            <span class="seg routine" style:width={`${(100 * combo.routine) / scale}%`}></span>
            {#each combo.parts as part (part!.area.id)}
              <span class="seg committed" style:width={`${(100 * part!.committed) / scale}%`} style:background={areaColor(part!.area.id)}></span>
            {/each}
            {#if !over}<span class="seg free" style:width={`${(100 * combo.free) / scale}%`}></span>{/if}
            <span class="cap" style:left={`${(100 * combo.capacity) / scale}%`}></span>
          </div>
          <span class="value" class:over>
            {#if over}
              <strong>⚠ over by {fmtHours(-combo.free)}{share(-combo.free, combo.capacity, " over")}</strong>
            {:else}
              <strong>{fmtHours(combo.free)} free{share(combo.free, combo.capacity)}</strong>
              <span class="muted">· ≈ {fmtHours(combo.freePerWeek)}/wk</span>
            {/if}
          </span>
          <span class="detail muted">
            capacity {fmtHours(combo.capacity)} · routine {fmtHours(combo.routine)} ·
            projects {combo.parts.map((part) => `${part!.area.label} ${fmtHours(part!.committed)}`).join(" + ")}
          </span>
          {@render breakdown(
            combo.parts.flatMap((part) => part!.committedBy).sort((a, b) => b.hours - a.hours),
            combo.parts.flatMap((part) => part!.routineBy).sort((a, b) => b.hours - a.hours),
          )}
        </div>
      {/if}
      <div class="h-total">
        <span class="name">All work</span>
        <span>
          capacity <strong>{fmtHours(total.capacity)}</strong> · routine {fmtHours(total.routine)} ·
          projects {fmtHours(total.committed)} ·
          {#if total.free >= 0}<strong>{fmtHours(total.free)} free{share(total.free, total.capacity)}</strong>{:else}<strong class="over">⚠ over by {fmtHours(-total.free)}{share(-total.free, total.capacity, " over")}</strong>{/if}
        </span>
      </div>
    </div>

    <!-- ================= projects ================= -->
    <div class="projects-head">
      <h2>Projects</h2>
      <label class="toggle"><input type="checkbox" bind:checked={showFinished} /> Show done and dropped</label>
    </div>

    {#each tax.areas as a (a.id)}
      {@const cats = tax.categories.filter((c) => c.area_id === a.id)}
      {@const plannable = cats.filter((c) => PLANNABLE_KINDS.has(c.kind))}
      {@const other = cats.filter((c) => !PLANNABLE_KINDS.has(c.kind) && projectsIn(c).length)}
      <div class="area" style:--area={areaColor(a.id)}>
        <h3>{a.label}</h3>

        {#snippet projectList(c: Category)}
          {#each projectsIn(c) as p (p.id)}
            {@const l = loads.get(p.id)!}
            {@const plan = plannedOf(p)}
            <div class="project" class:open={expanded === p.id} class:complete={p.status === "done"}>
              <div class="p-line">
              <button class="p-row" onclick={() => toggle(p.id)} aria-expanded={expanded === p.id}>
                <span class="p-name">
                  {#if p.is_important}<span class="star" title="Important">★</span>{/if}{p.name}<FolderLink url={p.folder_url} />
                  {#if p.group_project_id}<span class="shared" title={`Stands for the shared project “${sharedTitle(p)}”`}>⇄</span>{/if}
                  <span class="chip status-{p.status}">{p.status}</span>
                </span>
                <span class="p-dates muted">{period(p)}</span>
                <span class="meter" aria-hidden="true">
                  {#if plan.hours}
                    <span class="fill" style:width={`${Math.min(100, (100 * l.actual) / plan.hours)}%`}></span>
                  {/if}
                </span>
                <span class="p-hours">
                  <strong>{fmtHours(l.actual)}</strong>
                  {#if plan.hours !== null}<span class="muted" title={plan.fromMilestones ? "Sum of the milestones' planned hours" : ""}> of {fmtHours(plan.hours)}{plan.fromMilestones ? " Σ" : ""}</span>{/if}
                </span>
                <span class="p-flag" class:warn={warn(l)}>{warn(l) ? "⚠ " : ""}{flagText(l, p)}</span>
              </button>
              <input type="checkbox" class="p-done" checked={p.status === "done"}
                     title={p.status === "done" ? "Done — untick to reopen" : "Mark the project done"}
                     aria-label={`${p.name} done`}
                     onchange={(ev) => setComplete(p, (ev.target as HTMLInputElement).checked)} />
              </div>
              {#if expanded === p.id}
                <div class="p-body">
                  <ProjectEditor project={p} categories={editorCategories} categoryId={p.category_id} shared={sharedChoices}
                                 onsaved={changed} oncancel={() => (expanded = null)} />
                  <Milestones project={p} {actualByMilestone} {privateShared} onchange={load} />
                </div>
              {/if}
            </div>
          {/each}
        {/snippet}

        {#each plannable as c (c.id)}
          <div class="cat">
            <div class="cat-head">
              <span class="cat-name">{c.label}</span>
              <button class="add" onclick={() => startAdding(c.id)}>+ Project</button>
            </div>
            {#if addingTo === c.id}
              <div class="p-body new">
                <ProjectEditor project={null} categories={editorCategories} categoryId={c.id} shared={sharedChoices}
                               onsaved={changed} oncancel={() => (addingTo = null)} />
              </div>
            {/if}
            {@render projectList(c)}
            {#if !projectsIn(c).length && addingTo !== c.id}<p class="muted empty">No projects.</p>{/if}
          </div>
        {/each}

        {#if other.length}
          <details class="other">
            <summary>Projects in routine categories ({other.reduce((s, c) => s + projectsIn(c).length, 0)}) — counted in routine time, not the plan</summary>
            {#each other as c (c.id)}
              <div class="cat">
                <div class="cat-head"><span class="cat-name">{c.label}</span></div>
                {@render projectList(c)}
              </div>
            {/each}
          </details>
        {/if}
      </div>
    {/each}

    <!-- ================= categories ================= -->
    <details class="cats">
      <summary><h2>Categories</h2> <span class="muted">add, rename, change kind, and keep private notes</span></summary>
      <CategoryNotes {tax} onsaved={load} />
    </details>

    <!-- ================= allocation ================= -->
    <div class="projects-head">
      <h2>Allocation</h2>
      {#if !editingSettings}<button class="add" onclick={() => (editingSettings = true)}>Edit targets and settings</button>{/if}
    </div>
    {#if editingSettings}
      <div class="p-body new"><Settings {tax} onsaved={settingsSaved} oncancel={() => (editingSettings = false)} /></div>
    {/if}
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Area</th><th class="num">Time h/wk</th><th class="num">Email h/wk</th><th class="num">h/year</th></tr>
        </thead>
        <tbody>
          {#each tax.areas as a (a.id)}
            {@const t = targetOn(tax.targets, a.id, today())}
            <tr>
              <td>{a.label}</td>
              <td class="num">{t ? t.weekly_hours : "—"}</td>
              <td class="num">{t ? t.email_weekly_hours : "—"}</td>
              <td class="num">{t ? Math.round((t.weekly_hours + t.email_weekly_hours) * tax.weeksPerYear) : "—"}</td>
            </tr>
          {/each}
        </tbody>
        <tfoot>
          <tr>
            <td>Total · {tax.weeksPerYear} weeks</td>
            <td class="num">{tax.areas.reduce((s, a) => s + (targetOn(tax!.targets, a.id, today())?.weekly_hours ?? 0), 0)}</td>
            <td class="num">{tax.areas.reduce((s, a) => s + (targetOn(tax!.targets, a.id, today())?.email_weekly_hours ?? 0), 0)}</td>
            <td class="num">{Math.round(tax.areas.reduce((s, a) => {
              const t = targetOn(tax!.targets, a.id, today());
              return s + (t ? (t.weekly_hours + t.email_weekly_hours) * tax!.weeksPerYear : 0);
            }, 0))}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  {/if}

  <ExportData />
</section>

{#if flash}
  <div class="flash" role="status">
    <span>{flash.text}</span>
    {#if flash.undo}<button onclick={() => { flash = null; undoLast(); }}>Undo</button>{/if}
    <button class="x" aria-label="Dismiss" onclick={() => (flash = null)}>✕</button>
  </div>
{/if}

<style>
  .planning h2 { margin-top: 2.2rem; }
  .note { font-family: var(--font-ui); font-size: 0.85rem; margin: -0.2rem 0 0.6rem; max-width: 46rem; }

  /* ---- horizon ---- */
  .legend { display: flex; flex-wrap: wrap; gap: 1rem; font-family: var(--font-ui); font-size: 0.8rem; color: var(--ink-soft); margin-bottom: 0.9rem; }
  .legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
  .sw { display: inline-block; width: 12px; height: 10px; border-radius: 2px; }
  .sw.routine { background: var(--ink-soft); opacity: 0.55; }
  .sw.committed { background: linear-gradient(90deg, var(--series-1) 0 25%, var(--series-2) 25% 50%, var(--series-3) 50% 75%, var(--series-4) 75%); }
  .sw.free { background: var(--track); border: 1px solid var(--rule); }
  .sw.cap { width: 2px; height: 14px; background: var(--ink); border-radius: 0; }

  .horizon { display: grid; gap: 1rem; font-family: var(--font-ui); font-size: 0.92rem; }
  .h-row {
    display: grid;
    grid-template-columns: 7rem 1fr 12rem;
    grid-template-areas: "name stack value" ". detail detail";
    column-gap: 0.9rem;
    row-gap: 0.25rem;
    align-items: center;
  }
  .h-row .name { grid-area: name; font-weight: 600; }
  /* hover (or focus) a row to see its hours by project and by routine category */
  .h-row { position: relative; }
  .h-row:focus-visible { outline: 2px solid var(--accent, var(--ink)); outline-offset: 4px; border-radius: 2px; }
  .breakdown {
    display: none; position: absolute; z-index: 5; top: calc(100% + 0.3rem); left: 7.9rem;
    grid-template-columns: repeat(2, minmax(12rem, 16rem)); gap: 1.2rem;
    background: var(--paper, var(--bg)); border: 1px solid var(--rule); border-radius: 6px;
    padding: 0.6rem 0.8rem; box-shadow: 0 4px 14px rgb(0 0 0 / 0.12); font-size: 0.8rem;
  }
  .h-row:hover .breakdown, .h-row:focus-within .breakdown { display: grid; }
  .breakdown > div { display: grid; gap: 0.15rem; align-content: start; }
  .breakdown strong { font-weight: 600; margin-bottom: 0.15rem; }
  .breakdown > div > span { display: flex; justify-content: space-between; gap: 0.8rem; }
  .breakdown > div > span > span:last-child { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .stack { grid-area: stack; position: relative; display: flex; gap: 2px; height: 12px; }
  .seg { display: block; height: 100%; min-width: 0; }
  .seg:first-child { border-radius: 2px 0 0 2px; }
  .seg:nth-last-child(2) { border-radius: 0 4px 4px 0; }
  .seg.routine { background: var(--ink-soft); opacity: 0.55; }
  .seg.free { background: var(--track); }
  /* the combined row: set apart, thinner, stacked from its areas' own colours */
  .h-row.combo { border-top: 1px dashed var(--rule); padding-top: 0.8rem; }
  .h-row.combo .name { font-weight: 400; }
  .h-row.combo .tag { font-size: 0.68rem; color: var(--ink-soft); border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.35rem; font-style: normal; }
  .stack.thin { height: 7px; }
  .cap { position: absolute; top: -4px; bottom: -4px; width: 2px; margin-left: -1px; background: var(--ink); }
  .h-row .value { grid-area: value; font-variant-numeric: tabular-nums; }
  .h-row .detail { grid-area: detail; font-size: 0.8rem; }
  .over, .value.over strong { color: var(--danger); }
  .h-total { display: flex; gap: 0.9rem; flex-wrap: wrap; border-top: 1px solid var(--rule); padding-top: 0.7rem; }
  .h-total .name { width: 7rem; font-weight: 600; }

  /* ---- projects ---- */
  .projects-head { display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; }
  .projects-head h2 { margin-bottom: 0.4rem; }
  .toggle { display: inline-flex; align-items: center; gap: 0.4rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  .toggle input { width: auto; }

  .area { margin-top: 1.4rem; }
  .area h3 { font-size: 1.05rem; border-left: 4px solid var(--area); padding-left: 0.5rem; }
  .cat { margin: 0.8rem 0 0 0.9rem; }
  .cat-head { display: flex; align-items: center; gap: 0.75rem; font-family: var(--font-ui); }
  .cat-name { font-weight: 600; font-size: 0.9rem; color: var(--ink-soft); }
  .add { font-size: 0.8rem; padding: 0.15rem 0.6rem; }
  .empty { font-family: var(--font-ui); font-size: 0.82rem; margin: 0.2rem 0 0; }

  .cats { margin-top: 2.2rem; }
  .cats summary { cursor: pointer; font-family: var(--font-ui); }
  .cats summary h2 { display: inline; margin: 0; }
  .cats summary .muted { font-size: 0.82rem; margin-left: 0.4rem; }
  .cats[open] summary { margin-bottom: 0.8rem; }
  .project { border-radius: var(--radius); }
  .p-line { display: flex; align-items: flex-start; gap: 0.2rem; }
  .p-done { width: auto; flex: none; margin: 0.75rem 0.6rem 0 0.2rem; }
  .project.complete .p-name { text-decoration: line-through; color: var(--ink-soft); }
  .horizon-head { display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; }
  .horizon-pick { display: flex; gap: 0.25rem; font-family: var(--font-ui); }
  .horizon-pick button { font-size: 0.8rem; padding: 0.2rem 0.55rem; }
  .horizon-pick button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .flash {
    position: fixed; left: 50%; bottom: 1.2rem; transform: translateX(-50%); z-index: 60;
    display: flex; align-items: center; gap: 0.8rem; max-width: calc(100vw - 32px);
    padding: 0.55rem 0.6rem 0.55rem 1rem; background: var(--ink); color: var(--paper);
    border-radius: var(--radius); box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
    font-family: var(--font-ui); font-size: 0.88rem;
  }
  .flash button { background: none; border: 1px solid var(--paper); color: var(--paper); padding: 0.2rem 0.7rem; font-size: 0.82rem; }
  .flash button.x { border: none; padding: 0.2rem 0.4rem; opacity: 0.8; }
  .project.open { background: var(--panel); }
  .p-row {
    flex: 1;
    min-width: 0;
    width: 100%;
    display: grid;
    grid-template-columns: minmax(10rem, 1.6fr) 12rem minmax(5rem, 1fr) 8.5rem;
    grid-template-areas: "name dates meter hours" "flag flag flag flag";
    column-gap: 0.9rem;
    align-items: center;
    text-align: left;
    background: none;
    border: none;
    border-radius: var(--radius);
    padding: 0.5rem 0.5rem;
    font-size: 0.9rem;
  }
  .p-row:hover { background: var(--panel); }
  .p-name { grid-area: name; }
  .star { color: var(--ink); margin-right: 0.3rem; }
  .shared { color: var(--ink-soft); font-size: 0.8rem; margin-left: 0.3rem; }
  .p-dates { grid-area: dates; font-size: 0.8rem; }
  .meter { grid-area: meter; position: relative; display: block; height: 8px; background: var(--track); border-radius: 0 4px 4px 0; }
  .fill { position: absolute; inset: 0 auto 0 0; background: var(--area); border-radius: 0 4px 4px 0; min-width: 2px; }
  .p-hours { grid-area: hours; text-align: right; font-variant-numeric: tabular-nums; }
  .p-flag { grid-area: flag; font-size: 0.78rem; color: var(--ink-soft); }
  .p-flag:empty { display: none; }
  .p-flag.warn { color: var(--danger); }
  .p-body { padding: 0.4rem 0.6rem 1rem; }
  .p-body.new { background: var(--panel); border-radius: var(--radius); margin: 0.4rem 0; padding-top: 0.8rem; }

  .other { margin: 1rem 0 0 0.9rem; font-family: var(--font-ui); }
  .other summary { cursor: pointer; font-size: 0.85rem; color: var(--ink-soft); }

  /* ---- allocation ---- */
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; max-width: 36rem; font-family: var(--font-ui); font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--rule); }
  th { color: var(--ink-soft); font-weight: 500; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  tfoot td { border-bottom: none; font-weight: 600; }

  @media (max-width: 44rem) {
    .h-row { grid-template-columns: 1fr auto; grid-template-areas: "name value" "stack stack" "detail detail"; }
    .breakdown { left: 0; right: 0; grid-template-columns: 1fr; gap: 0.6rem; }
    .p-row {
      grid-template-columns: 1fr auto;
      grid-template-areas: "name hours" "meter meter" "dates dates" "flag flag";
      row-gap: 0.3rem;
    }
  }
</style>
