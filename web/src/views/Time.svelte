<script lang="ts">
  import { loadTaxonomy, loadEntryHours, targetOn, fmtHours } from "../lib/data";
  import type { Taxonomy, EntryHours } from "../lib/data";
  import { PRESETS, presetRange, addDays, today, daysIn, fmtDay } from "../lib/dates";
  import type { Preset, Range } from "../lib/dates";

  // ---- period ------------------------------------------------------------
  const PRESET_KEY = "time.preset";
  function savedPreset(): Preset {
    try {
      const p = localStorage.getItem(PRESET_KEY);
      if (p && PRESETS.some((x) => x.key === p)) return p as Preset;
    } catch {}
    return "this-month";
  }
  let preset = $state<Preset>(savedPreset());
  let custom = $state<Range>({ from: addDays(today(), -29), to: today() });
  const range = $derived(presetRange(preset, custom));

  function choose(p: Preset) {
    preset = p;
    try { localStorage.setItem(PRESET_KEY, p); } catch {}
  }

  // ---- data --------------------------------------------------------------
  let tax = $state<Taxonomy | null>(null);
  let entries = $state<EntryHours[]>([]);
  let loading = $state(true);
  let error = $state("");
  let request = 0;

  loadTaxonomy().then((t) => (tax = t)).catch((e) => (error = e.message));

  $effect(() => {
    const { from, to } = range;
    if (!from || !to || from > to) return;
    const id = ++request;
    loading = true;
    loadEntryHours(from, to)
      .then((rows) => { if (id === request) { entries = rows; error = ""; } })
      .catch((e) => { if (id === request) error = e.message; })
      .finally(() => { if (id === request) loading = false; });
  });

  // Colour follows the area (its place in the area order), never its rank.
  const areaIndex = $derived(new Map((tax?.areas ?? []).map((a, i) => [a.id, i])));
  function areaColor(areaId: string): string {
    const i = areaIndex.get(areaId) ?? 99;
    return i < 4 ? `var(--series-${i + 1})` : "var(--ink-soft)";
  }

  // ---- plan vs actual ----------------------------------------------------
  // Targets accrue day by day up to today: an annual allocation of
  // (weekly + email) × weeks_per_year spread over 365 days. A period that runs
  // into the future is judged on the days already lived.
  const elapsed = $derived.by(() => {
    const end = range.to < today() ? range.to : today();
    return end < range.from ? 0 : daysIn({ from: range.from, to: end });
  });
  const targetEnd = $derived(range.to < today() ? range.to : today());

  const plan = $derived.by(() => {
    if (!tax) return [];
    const perDay = tax.weeksPerYear / 365;
    return tax.areas.map((a) => {
      const t = targetOn(tax!.targets, a.id, targetEnd);
      const rows = entries.filter((e) => e.area_id === a.id);
      const actual = rows.reduce((s, e) => s + e.hours, 0);
      const email = rows.filter((e) => e.category_kind === "email").reduce((s, e) => s + e.hours, 0);
      const target = t ? (t.weekly_hours + t.email_weekly_hours) * perDay * elapsed : 0;
      const emailTarget = t ? t.email_weekly_hours * perDay * elapsed : 0;
      return { area: a, actual, target, email, emailTarget };
    });
  });
  const planMax = $derived(Math.max(1, ...plan.map((p) => Math.max(p.actual, p.target))));

  const totals = $derived.by(() => {
    const logged = entries.reduce((s, e) => s + e.hours, 0);
    const core = entries.filter((e) => e.is_core).reduce((s, e) => s + e.hours, 0);
    const target = plan.reduce((s, p) => s + p.target, 0);
    return { logged, core, target, perWeek: elapsed ? (logged / elapsed) * 7 : 0 };
  });

  // ---- composition drill-down -------------------------------------------
  // all work > area > category > project > milestone
  type Node = {
    key: string;
    label: string;
    sub: string;
    hours: number;
    count: number;
    areaId: string;
    none: boolean; // the "No project" / "No milestone" remainder
    children: Map<string, Node>;
  };

  function node(key: string, label: string, sub: string, areaId: string, none = false): Node {
    return { key, label, sub, hours: 0, count: 0, areaId, none, children: new Map() };
  }

  const tree = $derived.by(() => {
    const root = node("all", "All work", "", "");
    if (!tax) return root;
    const cats = new Map(tax.categories.map((c) => [c.id, c]));
    for (const a of tax.areas) root.children.set(a.id, node(a.id, a.label, "", a.id));
    for (const e of entries) {
      const area = root.children.get(e.area_id);
      if (!area) continue;
      const c = cats.get(e.category_id);
      const cat = getOr(area, e.category_id, () => node(e.category_id, c?.label ?? "Category", c?.kind ?? "", e.area_id));
      const pKey = e.project_id ?? "none";
      const proj = getOr(cat, pKey, () =>
        node(pKey, e.project_name ?? "No project", e.project_id ? "project" : "", e.area_id, !e.project_id));
      const path = [root, area, cat, proj];
      if (e.project_id) {
        const mKey = e.milestone_id ?? "none";
        path.push(getOr(proj, mKey, () =>
          node(mKey, e.milestone_title ?? "No milestone", e.milestone_id ? "milestone" : "", e.area_id, !e.milestone_id)));
      }
      for (const n of path) { n.hours += e.hours; n.count += 1; }
    }
    return root;
  });

  function getOr(parent: Node, key: string, make: () => Node): Node {
    let n = parent.children.get(key);
    if (!n) parent.children.set(key, (n = make()));
    return n;
  }

  let path = $state<string[]>([]);

  // Walk as far down the chosen path as this period's data allows.
  const trail = $derived.by(() => {
    const out = [tree];
    for (const k of path) {
      const next = out[out.length - 1].children.get(k);
      if (!next) break;
      out.push(next);
    }
    return out;
  });
  const current = $derived(trail[trail.length - 1]);
  const rows = $derived(
    [...current.children.values()].sort((p, q) => q.hours - p.hours || p.label.localeCompare(q.label)),
  );
  const rowMax = $derived(Math.max(1e-9, ...rows.map((r) => r.hours)));

  function drillable(n: Node): boolean {
    const kids = [...n.children.values()];
    return kids.length > 0 && !(kids.length === 1 && kids[0].none);
  }
  function drill(n: Node) {
    if (drillable(n)) path = [...trail.slice(1).map((t) => t.key), n.key];
  }
  function upTo(i: number) {
    path = trail.slice(1, i + 1).map((t) => t.key);
  }

  function pct(part: number, whole: number): string {
    return whole > 0 ? `${Math.round((100 * part) / whole)}%` : "—";
  }
</script>

<section class="time">
  <span class="eyebrow">Time</span>
  <h1>Where the time goes</h1>

  <div class="filters" role="group" aria-label="Period">
    {#each PRESETS as p (p.key)}
      <button class:on={preset === p.key} aria-pressed={preset === p.key} onclick={() => choose(p.key)}>{p.label}</button>
    {/each}
  </div>
  {#if preset === "custom"}
    <div class="custom">
      <label>From <input type="date" bind:value={custom.from} max={custom.to} /></label>
      <label>To <input type="date" bind:value={custom.to} min={custom.from} /></label>
    </div>
  {/if}
  <p class="muted period">
    {fmtDay(range.from)} – {fmtDay(range.to)}
    {#if loading}<span class="loading">· loading…</span>{/if}
  </p>

  {#if error}
    <p class="error">{error}</p>
  {:else if tax}
    <!-- KPI row -->
    <div class="kpis">
      <div class="kpi">
        <span class="kpi-label">Logged</span>
        <span class="kpi-value">{fmtHours(totals.logged)}</span>
        <span class="kpi-sub">{pct(totals.logged, totals.target)} of target to date</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Target to date</span>
        <span class="kpi-value">{fmtHours(totals.target)}</span>
        <span class="kpi-sub">{elapsed} of {daysIn(range)} days elapsed</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Weekly average</span>
        <span class="kpi-value">{fmtHours(totals.perWeek)}</span>
        <span class="kpi-sub">per week, over days elapsed</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Core</span>
        <span class="kpi-value">{pct(totals.core, totals.logged)}</span>
        <span class="kpi-sub">{fmtHours(totals.core)} flagged core</span>
      </div>
    </div>

    <!-- Plan vs actual -->
    <h2>Plan vs actual</h2>
    <p class="muted note">Bars are hours logged; the tick is the target for the days elapsed.</p>
    <div class="plan">
      {#each plan as p (p.area.id)}
        <div class="plan-row" title={`${p.area.label}: ${fmtHours(p.actual)} logged, target ${fmtHours(p.target)}`}>
          <span class="name">{p.area.label}</span>
          <div class="track" aria-hidden="true">
            <div class="bar" style:width={`${(100 * p.actual) / planMax}%`} style:background={areaColor(p.area.id)}></div>
            {#if p.target > 0}<div class="tick" style:left={`${(100 * p.target) / planMax}%`}></div>{/if}
          </div>
          <span class="value">
            <strong>{fmtHours(p.actual)}</strong> of {fmtHours(p.target)}
            <span class="muted">· {pct(p.actual, p.target)}</span>
          </span>
          {#if p.emailTarget > 0 || p.email > 0}
            <span class="email muted">email {fmtHours(p.email)} of {fmtHours(p.emailTarget)}</span>
          {/if}
        </div>
      {/each}
    </div>

    <!-- Composition -->
    <h2>Composition</h2>
    <nav class="crumbs" aria-label="Drill-down level">
      {#each trail as t, i (t.key + i)}
        {#if i > 0}<span class="sep" aria-hidden="true">›</span>{/if}
        {#if i < trail.length - 1}
          <button class="crumb" onclick={() => upTo(i)}>{t.label}</button>
        {:else}
          <span class="crumb here" aria-current="location">{t.label}</span>
        {/if}
      {/each}
      <span class="muted crumb-total">{fmtHours(current.hours)}</span>
    </nav>

    {#if !rows.length || current.hours === 0}
      <p class="muted">Nothing logged here in this period.</p>
    {:else}
      <ol class="rows">
        {#each rows as r (r.key)}
          {@const canDrill = drillable(r)}
          <li>
            <button
              class="row"
              class:none={r.none}
              disabled={!canDrill}
              onclick={() => drill(r)}
              title={`${r.label}: ${fmtHours(r.hours)}, ${r.count} ${r.count === 1 ? "entry" : "entries"}`}
            >
              <span class="name">
                {r.label}
                {#if r.sub}<small>{r.sub}</small>{/if}
              </span>
              <span class="track" aria-hidden="true">
                <span class="bar" style:width={`${(100 * r.hours) / rowMax}%`} style:background={areaColor(r.areaId)}></span>
              </span>
              <span class="value"><strong>{fmtHours(r.hours)}</strong> <span class="muted">· {pct(r.hours, current.hours)}</span></span>
              <span class="chev" aria-hidden="true">{canDrill ? "›" : ""}</span>
            </button>
          </li>
        {/each}
      </ol>
    {/if}
  {/if}
</section>

<style>
  .time h2 { margin-top: 2.2rem; }
  .filters { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 1rem; }
  .filters button { font-size: 0.88rem; padding: 0.35rem 0.75rem; }
  .filters button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .custom { display: flex; gap: 0.75rem; margin-top: 0.6rem; max-width: 26rem; }
  .custom label { flex: 1; display: grid; gap: 0.2rem; font-family: var(--font-ui); font-size: 0.82rem; color: var(--ink-soft); }
  .period { font-family: var(--font-ui); font-size: 0.88rem; margin: 0.6rem 0 0; }
  .note { font-family: var(--font-ui); font-size: 0.85rem; margin: -0.2rem 0 0.8rem; }

  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: 0.75rem;
    margin-top: 1.25rem;
  }
  .kpi {
    display: grid;
    gap: 0.15rem;
    background: var(--panel);
    border-radius: var(--radius);
    padding: 0.8rem 1rem;
    font-family: var(--font-ui);
  }
  .kpi-label { font-size: 0.78rem; color: var(--ink-soft); }
  .kpi-value { font-size: 1.6rem; font-weight: 600; line-height: 1.2; }
  .kpi-sub { font-size: 0.78rem; color: var(--ink-soft); }

  /* shared bar anatomy: thin, rounded data end, anchored to the left */
  .track { position: relative; display: block; height: 10px; background: var(--track); border-radius: 0 4px 4px 0; }
  .bar { position: absolute; inset: 0 auto 0 0; display: block; border-radius: 0 4px 4px 0; min-width: 2px; }

  .plan { display: grid; gap: 0.9rem; font-family: var(--font-ui); font-size: 0.92rem; }
  .plan-row {
    display: grid;
    grid-template-columns: 7rem 1fr 11rem;
    grid-template-areas: "name track value" ". email email";
    align-items: center;
    column-gap: 0.9rem;
  }
  .plan-row .name { grid-area: name; font-weight: 600; }
  .plan-row .track { grid-area: track; }
  .plan-row .value { grid-area: value; font-variant-numeric: tabular-nums; }
  .plan-row .email { grid-area: email; font-size: 0.8rem; }
  .tick {
    position: absolute;
    top: -4px;
    bottom: -4px;
    width: 2px;
    margin-left: -1px;
    background: var(--ink);
  }

  .crumbs {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.35rem;
    font-family: var(--font-ui);
    font-size: 0.92rem;
    margin-bottom: 0.6rem;
  }
  .crumb { background: none; border: none; padding: 0.15rem 0.2rem; color: var(--accent); text-decoration: underline; }
  .crumb.here { font-weight: 600; color: var(--ink); }
  .sep { color: var(--ink-soft); }
  .crumb-total { margin-left: auto; }

  .rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .row {
    width: 100%;
    display: grid;
    grid-template-columns: minmax(8rem, 16rem) 1fr 9rem 1rem;
    align-items: center;
    column-gap: 0.9rem;
    text-align: left;
    background: none;
    border: none;
    border-radius: var(--radius);
    padding: 0.55rem 0.5rem;
    font-family: var(--font-ui);
    font-size: 0.92rem;
  }
  .row:not(:disabled):hover { background: var(--panel); }
  .row:disabled { cursor: default; opacity: 1; }
  .row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row .name small { color: var(--ink-soft); margin-left: 0.4rem; font-size: 0.75rem; }
  .row.none .name { color: var(--ink-soft); font-style: italic; }
  .row.none .bar { opacity: 0.45; }
  .row .value { font-variant-numeric: tabular-nums; text-align: right; }
  .chev { color: var(--ink-soft); }

  @media (max-width: 40rem) {
    .plan-row {
      grid-template-columns: 1fr auto;
      grid-template-areas: "name value" "track track" "email email";
      row-gap: 0.35rem;
    }
    .row {
      grid-template-columns: 1fr auto 1rem;
      grid-template-areas: "name value chev" "track track track";
      row-gap: 0.35rem;
    }
    .row .name { grid-area: name; }
    .row .track { grid-area: track; }
    .row .value { grid-area: value; }
    .row .chev { grid-area: chev; }
  }
</style>
