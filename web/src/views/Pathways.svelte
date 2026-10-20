<script lang="ts">
  import { loadProjects, loadTaxonomy, setProjectDates } from "../lib/data";
  import type { Project, Taxonomy } from "../lib/data";
  import { LIVE_STATUSES } from "../lib/plan";
  import { loadReadings } from "../lib/reading";
  import type { Reading } from "../lib/reading";
  import {
    LANES, NODE_KINDS, LINK_KINDS, loadPathways, saveYears, saveNode, saveLink, inferLinkKind,
    monthStart, addMonths, fraction, monthAt, monthsBetween, shiftMonths,
  } from "../lib/pathways";
  import type { PwNode, PwLink, PwNodeFields, NodeKind, Lane } from "../lib/pathways";
  import { today, fmtDay } from "../lib/dates";
  import PwEditor from "../lib/PwEditor.svelte";
  import InfoSystem from "../lib/InfoSystem.svelte";
  import AssetEditor from "../lib/AssetEditor.svelte";
  import { loadAssets } from "../lib/assets";
  import type { Asset } from "../lib/assets";

  // ---- data -----------------------------------------------------------------------
  let nodes = $state<PwNode[]>([]);
  let links = $state<PwLink[]>([]);
  let years = $state(5);
  let projects = $state<Project[]>([]);
  let tax = $state<Taxonomy | null>(null);
  let assets = $state<Asset[]>([]);

  // two views of the same pathways: the map, and the information system
  const VIEW_KEY = "pathways.view";
  function savedView(): "map" | "system" {
    try { return localStorage.getItem(VIEW_KEY) === "system" ? "system" : "map"; } catch { return "map"; }
  }
  let view = $state<"map" | "system">(savedView());
  function setView(v: "map" | "system") {
    view = v;
    try { localStorage.setItem(VIEW_KEY, v); } catch {}
  }
  let readings = $state<Reading[]>([]);
  let loading = $state(true);
  let error = $state("");
  let showAll = $state(false);

  async function load() {
    try {
      const [pw, p, r, t, as] = await Promise.all([
        loadPathways(), loadProjects(), loadReadings().catch(() => [] as Reading[]), loadTaxonomy(),
        loadAssets().catch(() => [] as Asset[]), // before 0011 is run there are simply none
      ]);
      tax = t;
      assets = as;
      nodes = pw.nodes;
      links = pw.links;
      years = pw.years;
      projects = p;
      readings = r;
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  async function setYears(y: number) {
    years = y;
    try { await saveYears(y); } catch (e) { error = (e as Error).message; }
  }

  // ---- geometry -------------------------------------------------------------------
  const LABEL_W = 110, GOAL_W = 250, GAP = 18, AXIS_H = 30, ROW_H = 58, NODE_H = 44, PAD = 10, MIN_W = 96;
  let width = $state(1000);
  const mapW = $derived(Math.max(width, 980));
  const x0 = LABEL_W;
  const x1 = $derived(mapW - GOAL_W - GAP);
  const from = $derived(monthStart(today()));
  const to = $derived(addMonths(from, years * 12));
  const xOf = (iso: string) => x0 + Math.min(1, Math.max(0, fraction(iso, from, to))) * (x1 - x0);

  // An item linked to a Planning project shows that project's current name and
  // dates (and is done once the project is); moving it moves the project.
  const projById = $derived(new Map(projects.map((p) => [p.id, p])));
  function eff(n: PwNode): PwNode {
    const p = n.project_id ? projById.get(n.project_id) : undefined;
    if (!p) return n;
    return {
      ...n,
      title: p.name,
      start_on: p.start_on ?? n.start_on,
      end_on: p.end_on ?? n.end_on,
      status: p.status === "done" || p.status === "dropped" ? "done" : n.status,
    };
  }
  const visible = $derived(nodes.map(eff).filter((n) => showAll || n.status === "active"));

  // ---- dragging (move / stretch / link) -------------------------------------------
  type Drag =
    | { mode: "move" | "resize"; id: string; px: number; py: number; moved: boolean;
        start: string; end: string; lane: Lane; row: number }
    | { mode: "link"; id: string; x: number; y: number };
  let drag = $state<Drag | null>(null);
  let mapEl = $state<HTMLDivElement | null>(null);

  /** A node as it should be drawn: with the drag applied, if it is the one moving. */
  function shown(n: PwNode): PwNode {
    if (drag && drag.mode !== "link" && drag.id === n.id && drag.moved) {
      return { ...n, start_on: n.kind === "goal" ? null : drag.start, end_on: n.kind === "goal" ? null : drag.end, lane: drag.lane, lane_row: drag.row };
    }
    return n;
  }
  const drawn = $derived(visible.map(shown));

  const laneRows = $derived(
    Object.fromEntries(LANES.map((l) => [l.key, Math.max(0, ...drawn.filter((n) => n.lane === l.key).map((n) => n.lane_row)) + 2])),
  );
  const laneTop = $derived.by(() => {
    const out: Record<string, number> = {};
    let y = AXIS_H;
    for (const l of LANES) { out[l.key] = y; y += laneRows[l.key] * ROW_H + 2 * PAD; }
    return out;
  });
  const mapH = $derived(LANES.reduce((y, l) => y + laneRows[l.key] * ROW_H + 2 * PAD, AXIS_H) + 8);

  type Box = { x: number; y: number; w: number; open: boolean };
  function box(n: PwNode): Box {
    const y = laneTop[n.lane] + PAD + n.lane_row * ROW_H;
    if (n.kind === "goal") return { x: x1 + GAP, y, w: GOAL_W - 10, open: false };
    const s = n.start_on ?? today();
    const e = n.end_on ?? addMonths(monthStart(s), 3);
    const left = xOf(s < from ? from : s);
    const right = xOf(e > to ? to : e);
    return { x: left, y, w: Math.max(MIN_W, right - left), open: !n.end_on };
  }
  const boxes = $derived(new Map(drawn.map((n) => [n.id, box(n)])));

  function local(ev: PointerEvent) {
    const r = mapEl!.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  }
  function laneAt(y: number): { lane: Lane; row: number } {
    let lane: Lane = LANES[LANES.length - 1].key;
    for (const l of LANES) if (y >= laneTop[l.key]) lane = l.key;
    return { lane, row: Math.max(0, Math.min(laneRows[lane] - 1, Math.floor((y - laneTop[lane] - PAD) / ROW_H))) };
  }

  function begin(ev: PointerEvent, n: PwNode, mode: "move" | "resize" | "link") {
    if (ev.button !== 0) return;
    ev.preventDefault();
    ev.stopPropagation();
    const p = local(ev);
    if (mode === "link") {
      drag = { mode, id: n.id, x: p.x, y: p.y };
    } else {
      const s = n.start_on ?? today();
      drag = { mode, id: n.id, px: p.x, py: p.y, moved: false,
               start: s, end: n.end_on ?? addMonths(monthStart(s), 3), lane: n.lane, row: n.lane_row };
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  function onMove(ev: PointerEvent) {
    if (!drag || !mapEl) return;
    const p = local(ev);
    if (drag.mode === "link") {
      drag = { ...drag, x: p.x, y: p.y };
      return;
    }
    const n = eff(nodes.find((x) => x.id === drag!.id)!);
    const dx = p.x - drag.px, dy = p.y - drag.py;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;
    // dates move by whole months and keep their day, so a Planning project's
    // exact dates survive a drag (30 Jun moved 7 months is 30 Jan)
    const s0 = n.start_on ?? today();
    const e0 = n.end_on ?? addMonths(monthStart(s0), 3);
    const f = (x: number) => (x - x0) / (x1 - x0);
    if (drag.mode === "resize") {
      const k = monthsBetween(monthStart(e0), monthAt(f(xOf(e0) + dx), from, to));
      let end = shiftMonths(e0, k);
      if (end <= s0) end = shiftMonths(s0, 1);
      drag = { ...drag, moved: true, end };
    } else {
      const k = n.kind === "goal" ? 0 : monthsBetween(monthStart(s0 < from ? from : s0), monthAt(f(xOf(s0 < from ? from : s0) + dx), from, to));
      const where = laneAt(p.y);
      drag = { ...drag, moved: true, start: shiftMonths(s0, k), end: shiftMonths(e0, k), lane: where.lane, row: where.row };
    }
  }

  async function onUp(ev: PointerEvent) {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    const d = drag;
    drag = null;
    if (!d) return;
    const raw = nodes.find((x) => x.id === d.id);
    const n = raw ? eff(raw) : undefined;
    if (!n) return;
    try {
      if (d.mode === "link") {
        const target = (document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null)?.closest<HTMLElement>("[data-node]");
        const to = target ? nodes.find((x) => x.id === target.dataset.node) : null;
        if (to && to.id !== n.id) {
          await saveLink(n.id, to.id, inferLinkKind(n, to));
          await load();
        }
        return;
      }
      if (!d.moved) return openEdit(raw!); // a click
      const fields: Partial<PwNodeFields> = { lane: d.lane, lane_row: d.row };
      if (n.kind !== "goal") Object.assign(fields, { start_on: d.start, end_on: d.end });
      // show it where it was dropped straight away; the reload confirms
      nodes = nodes.map((x) => (x.id === n.id ? { ...x, ...fields } as PwNode : x));
      if (n.project_id && n.kind !== "goal") {
        projects = projects.map((p) => (p.id === n.project_id ? { ...p, start_on: d.start, end_on: d.end } : p));
        await setProjectDates(n.project_id, d.start, d.end);
      }
      await saveNode(n.id, fields);
      await load();
    } catch (e) {
      error = (e as Error).message;
      await load();
    }
  }

  // ---- links drawn as curves --------------------------------------------------------
  const drawnLinks = $derived(
    links
      .map((l) => ({ l, a: boxes.get(l.from_id), b: boxes.get(l.to_id) }))
      .filter((x): x is { l: PwLink; a: Box; b: Box } => !!x.a && !!x.b)
      .map(({ l, a, b }) => {
        const ax = a.x + a.w, ay = a.y + NODE_H / 2;
        const forward = b.x >= ax - 4;
        const bx = forward ? b.x : b.x + b.w, by = b.y + NODE_H / 2;
        const dx = Math.max(40, Math.abs(bx - ax) / 2) * (forward ? 1 : -1);
        return { l, d: `M ${ax} ${ay} C ${ax + Math.abs(dx)} ${ay}, ${bx - dx} ${by}, ${bx} ${by}` };
      }),
  );
  const nodeTitle = (id: string) => nodes.find((x) => x.id === id)?.title ?? "";
  const linkLabel = (k: string) => LINK_KINDS.find((x) => x.key === k)?.label ?? k;

  // ---- axis ------------------------------------------------------------------------
  const ticks = $derived.by(() => {
    const out: { x: number; label: string; major: boolean }[] = [];
    const step = years <= 3 ? 3 : years <= 6 ? 6 : 12;
    for (let m = 0; m < years * 12; m += step) { // the horizon itself is named in the goals heading
      const iso = addMonths(from, m);
      out.push({ x: xOf(iso), label: step === 12 || iso.slice(5, 7) === "01" ? iso.slice(0, 4) : fmtDay(iso).replace(/^1 /, ""), major: iso.slice(5, 7) === "01" });
    }
    return out;
  });
  const todayX = $derived(xOf(today()));

  // ---- adding and editing ------------------------------------------------------------
  let panel = $state<{ node: PwNode | null; draft?: Partial<PwNodeFields> } | { importing: true } | { asset: Asset | null } | null>(null);
  const knownIO = $derived([...new Set(assets.flatMap((a) => [...a.inputs, ...a.outputs]))].sort((a, b) => a.localeCompare(b)));
  const assetCount = (id: string) => assets.filter((a) => a.status !== "retired" && (a.owner_node_id === id || a.project_node_id === id)).length;
  let dialog = $state<HTMLDialogElement | null>(null);
  $effect(() => {
    if (!dialog) return;
    if (panel && !dialog.open) dialog.showModal();
    if (!panel && dialog.open) dialog.close();
  });

  function openEdit(n: PwNode) { panel = { node: n }; }

  const DEFAULT_MONTHS: Record<NodeKind, number> = { goal: 0, objective: 12, project: 12, person: 3 * 12, gap: 6, grant: 3 };
  /** The first row in a lane free over a span (goals: the first free row in the goals column). */
  function freeRow(lane: Lane, kind: NodeKind, s: string, e: string, also: PwNode[] = []): number {
    const inLane = [...visible, ...also].filter((n) => n.lane === lane && (kind === "goal") === (n.kind === "goal"));
    for (let row = 0; ; row++) {
      const clash = inLane.some((n) => n.lane_row === row && (kind === "goal" ||
        ((n.start_on ?? today()) <= e && (n.end_on ?? addMonths(n.start_on ?? today(), 3)) >= s)));
      if (!clash) return row;
    }
  }
  function openNew(kind: NodeKind) {
    const lane = (NODE_KINDS.find((k) => k.key === kind)?.lane ?? "research") as Lane;
    const s = monthStart(today());
    const e = addMonths(s, DEFAULT_MONTHS[kind]);
    panel = {
      node: null,
      draft: {
        kind, lane, potential: kind === "project", grant_stage: kind === "grant" ? "drafting" : null,
        start_on: kind === "goal" ? null : s, end_on: kind === "goal" ? null : e,
        lane_row: freeRow(lane, kind, s, e),
      },
    };
  }
  // ---- bring existing Planning projects onto the map ------------------------------------
  // Each lands in its area's lane (student projects under Supervision go to the
  // Supervision lane), keeps the project's dates, and stays linked to it.
  type ImportRow = { p: Project; group: string; lane: Lane; kind: "project" | "grant"; already: boolean; pick: boolean };
  let importRows = $state<ImportRow[]>([]);
  let importing = $state(false);

  function laneFor(p: Project): { lane: Lane; kind: "project" | "grant"; group: string } {
    const c = tax?.allCategories.find((x) => x.id === p.category_id);
    const a = tax?.areas.find((x) => x.id === c?.area_id);
    const group = `${a?.label ?? "Other"} › ${c?.label ?? "—"}`;
    if (c?.code === "RES_PROP") return { lane: "grants", kind: "grant", group };
    if (c?.code === "RES_SUP") return { lane: "supervision", kind: "project", group };
    if (a?.code === "TEA") return { lane: "teaching", kind: "project", group };
    if (a?.code === "OUT") return { lane: "outreach", kind: "project", group };
    return { lane: "research", kind: "project", group };
  }
  function openImport() {
    const onMap = new Set(nodes.map((n) => n.project_id).filter(Boolean));
    importRows = projects
      .filter((p) => LIVE_STATUSES.has(p.status))
      .map((p) => ({ p, ...laneFor(p), already: onMap.has(p.id), pick: false }))
      .sort((a, b) => a.group.localeCompare(b.group) || a.p.name.localeCompare(b.p.name));
    panel = { importing: true };
  }
  const importGroups = $derived(
    [...new Set(importRows.map((r) => r.group))].map((g) => ({ group: g, rows: importRows.filter((r) => r.group === g) })),
  );
  async function addImported() {
    importing = true;
    const placed: PwNode[] = [];
    try {
      for (const r of importRows.filter((x) => x.pick && !x.already)) {
        const s = r.p.start_on ? monthStart(r.p.start_on) : monthStart(today());
        const e = r.p.end_on ?? null;
        const row = freeRow(r.lane, r.kind, s, e ?? addMonths(s, 3), placed);
        const fields: Partial<PwNodeFields> = {
          kind: r.kind, lane: r.lane, title: r.p.name, project_id: r.p.id, potential: false,
          grant_stage: r.kind === "grant" ? "drafting" : null,
          start_on: s, end_on: e, lane_row: row,
        };
        const id = await saveNode(null, fields);
        placed.push({ ...(fields as PwNode), id });
      }
    } catch (e) {
      error = (e as Error).message;
    } finally {
      importing = false;
    }
    panel = null;
    await load();
  }

  async function saved() {
    panel = null;
    await load();
  }

  const kindLabel = (k: string) => NODE_KINDS.find((x) => x.key === k)?.label ?? k;
  const nodeById = $derived(new Map(nodes.map((n) => [n.id, n])));
  /** Funding of an item from grants: "funded" once one is awarded, "funding pending" while any is open. */
  function funding(id: string): "funded" | "funding pending" | null {
    const stages = links.filter((l) => l.kind === "funds" && l.to_id === id).map((l) => nodeById.get(l.from_id)?.grant_stage ?? "drafting");
    if (stages.includes("awarded")) return "funded";
    return stages.some((s) => s !== "declined") ? "funding pending" : null;
  }
  /** A funding link is uncertain until its grant is awarded. */
  const linkStage = (l: PwLink) => (l.kind === "funds" ? nodeById.get(l.from_id)?.grant_stage ?? "drafting" : null);
  function sub(n: PwNode): string {
    const bits: string[] = [n.potential ? "potential project" : n.kind === "grant" ? `grant · ${n.grant_stage ?? "drafting"}` : kindLabel(n.kind).toLowerCase()];
    if (n.kind === "grant" && n.end_on) bits.push(`deadline ${fmtDay(n.end_on)}`);
    else if (n.kind !== "goal" && n.start_on) bits.push(`${n.start_on.slice(0, 7)} → ${n.end_on ? n.end_on.slice(0, 7) : "…"}`);
    if (n.kind === "grant" && n.cost) bits.push(n.cost.toLocaleString());
    const fu = funding(n.id);
    if (fu) bits.push(fu);
    if (n.effort_pm) bits.push(`${n.effort_pm} pm`);
    if (n.fte) bits.push(`${Math.round(n.fte * 100)}%`);
    const k = assetCount(n.id);
    if (k) bits.push(`${k} ${k === 1 ? "asset" : "assets"}`);
    return bits.join(" · ");
  }
</script>

<section class="pathways">
  <span class="eyebrow">Pathways</span>
  <h1>Pathways</h1>

  <div class="views" role="tablist" aria-label="Pathways view">
    <button role="tab" aria-selected={view === "map"} class:on={view === "map"} onclick={() => setView("map")}>Map</button>
    <button role="tab" aria-selected={view === "system"} class:on={view === "system"} onclick={() => setView("system")}>Information system</button>
  </div>

  {#if view === "system"}
    <InfoSystem {assets} {nodes} onadd={() => (panel = { asset: null })} onedit={(a) => (panel = { asset: a })} />
  {:else}
  <div class="toolbar">
    {#each NODE_KINDS as k (k.key)}
      <button class:primary={k.key === "project"} onclick={() => openNew(k.key)}>+ {k.label}</button>
    {/each}
    <button onclick={openImport} title="Put existing Planning projects on the map, linked to them">+ From Planning</button>
    <span class="spacer"></span>
    <div class="years" role="group" aria-label="How far ahead">
      {#each [3, 5, 10, 15, 20] as y (y)}
        <button class:on={years === y} aria-pressed={years === y} onclick={() => setYears(y)}>{y} yr</button>
      {/each}
    </div>
    <label class="toggle"><input type="checkbox" bind:checked={showAll} /> Show done and retired</label>
  </div>
  <div class="legend muted" aria-hidden="true">
    {#each LINK_KINDS as k (k.key)}<span><i class="lk {k.key}"></i>{k.label}</span>{/each}
    <span class="hint">Drag an item to move it in time or across lanes · drag its right edge to stretch it · drag its ○ onto another item to link them · click to edit</span>
  </div>

  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{/if}

  <div class="scroller" bind:clientWidth={width}>
    <div class="map" bind:this={mapEl} style:width={`${mapW}px`} style:height={`${mapH}px`} class:dragging={!!drag}>
      <!-- lanes -->
      {#each LANES as l, i (l.key)}
        <div class="lane lane-{l.key}" class:alt={i % 2 === 1} style:top={`${laneTop[l.key]}px`}
             style:height={`${laneRows[l.key] * ROW_H + 2 * PAD}px`}>
          <span class="lane-label">{l.label}</span>
        </div>
      {/each}
      <!-- axis -->
      {#each ticks as t (t.x)}
        <div class="tick" class:major={t.major} style:left={`${t.x}px`} style:height={`${mapH - 6}px`}><span>{t.label}</span></div>
      {/each}
      <div class="now" style:left={`${todayX}px`} style:height={`${mapH - 6}px`}><span>now</span></div>
      <div class="goals-head" style:left={`${x1 + GAP}px`} style:width={`${GOAL_W - 10}px`}>Goals · by {fmtDay(to).replace(/^1 /, "")}</div>

      <!-- links -->
      <svg class="links" width={mapW} height={mapH} aria-hidden="true">
        <defs>
          {#each LINK_KINDS as k (k.key)}
            <marker id={`arrow-${k.key}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L8,4 L0,8 z" class={`ah ${k.key}`} />
            </marker>
          {/each}
        </defs>
        {#each drawnLinks as dl (dl.l.id)}
          <path d={dl.d} class={`lk-path ${dl.l.kind} ${linkStage(dl.l) ?? ""}`} marker-end={`url(#arrow-${dl.l.kind})`}>
            <title>{nodeTitle(dl.l.from_id)} {linkLabel(dl.l.kind)} {nodeTitle(dl.l.to_id)}</title>
          </path>
        {/each}
        {#if drag?.mode === "link"}
          {@const a = boxes.get(drag.id)}
          {#if a}<path class="lk-path drawing" d={`M ${a.x + a.w} ${a.y + NODE_H / 2} L ${drag.x} ${drag.y}`} />{/if}
        {/if}
      </svg>

      <!-- items -->
      {#each drawn as n (n.id)}
        {@const b = boxes.get(n.id)!}
        <div class="node kind-{n.kind} lane-{n.lane} {n.kind === "grant" ? `gs-${n.grant_stage ?? "drafting"}` : ""}" class:potential={n.potential} class:open-end={b.open}
             class:inactive={n.status !== "active"} class:moving={drag?.id === n.id}
             data-node={n.id} role="button" tabindex="0" title={`${n.title}${n.detail ? `\n${n.detail}` : ""}`}
             style:left={`${b.x}px`} style:top={`${b.y}px`} style:width={`${b.w}px`} style:height={`${NODE_H}px`}
             onpointerdown={(ev) => begin(ev, n, "move")}
             onkeydown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openEdit(n); } }}>
          <span class="n-title">{n.kind === "goal" ? "◎ " : n.kind === "gap" ? "? " : ""}{n.title}</span>
          <span class="n-sub">{n.status !== "active" ? `${n.status} · ` : ""}{sub(n)}</span>
          {#if n.kind !== "goal"}
            <!-- pointer shortcuts; the editor's dates and Links do the same by keyboard -->
            <span class="resize" role="presentation" aria-hidden="true" title="Drag to change the end" onpointerdown={(ev) => begin(ev, n, "resize")}></span>
          {/if}
          <span class="connector" role="presentation" aria-hidden="true" title="Drag onto another item to link them" onpointerdown={(ev) => begin(ev, n, "link")}>○</span>
        </div>
      {/each}
    </div>
  </div>

  {#if !loading && !nodes.length}
    <p class="muted">Nothing on the map yet. Start with a goal on the right, then add projects and link them towards it.</p>
  {/if}
  {/if}
</section>

<dialog bind:this={dialog} onclose={() => (panel = null)}>
  {#if panel && "importing" in panel}
    <h2>Projects from Planning</h2>
    <p class="muted small">Tick the projects to put on the map. Each lands in its area's lane with its dates, linked to the Planning project.</p>
    {#if !importRows.length}
      <p class="muted">No live projects in Planning.</p>
    {/if}
    <div class="imp">
      {#each importGroups as g (g.group)}
        <details class="imp-group" open={g.rows.some((r) => !r.already)}>
          <summary><strong>{g.group}</strong> <span class="muted">{g.rows.length}</span></summary>
          {#each g.rows as r (r.p.id)}
            <label class="imp-row" class:off={r.already}>
              <input type="checkbox" bind:checked={r.pick} disabled={r.already} />
              <span class="imp-name">{r.p.name}</span>
              <span class="muted">
                {r.p.start_on || r.p.end_on ? `${r.p.start_on ?? "…"} → ${r.p.end_on ?? "…"}` : "no dates"}
                · {LANES.find((l) => l.key === r.lane)?.label} lane{r.already ? " · already on the map" : ""}
              </span>
            </label>
          {/each}
        </details>
      {/each}
    </div>
    <div class="imp-actions">
      {#if importRows.some((r) => r.pick && !r.already)}
        {@const n = importRows.filter((r) => r.pick && !r.already).length}
        <button class="primary" disabled={importing} onclick={addImported}>{importing ? "Adding…" : `Add ${n} to the map`}</button>
      {:else}
        <button class="primary" disabled>Tick projects to add</button>
      {/if}
      <button onclick={() => (panel = null)}>Cancel</button>
    </div>
  {:else if panel && "asset" in panel}
    <h2>{panel.asset ? "Edit asset" : "New asset"}</h2>
    {#key panel}
      <AssetEditor asset={panel.asset} {nodes} known={knownIO} onsaved={saved} oncancel={() => (panel = null)} />
    {/key}
  {:else if panel && "node" in panel}
    <h2>{panel.node ? `Edit ${kindLabel(panel.node.kind).toLowerCase()}` : `New ${kindLabel(panel.draft?.kind ?? "project").toLowerCase()}`}</h2>
    {#key panel}
      <PwEditor node={panel.node} draft={panel.draft} {nodes} {links} {projects} {readings} onsaved={saved} oncancel={() => (panel = null)} />
    {/key}
  {/if}
</dialog>

<style>
  .pathways {
    --lane-research: var(--series-1);
    --lane-teaching: var(--series-2);
    --lane-outreach: var(--series-4);
    --lane-supervision: #6250d6;
    --lane-grants: var(--series-3);
    --lk-funds: var(--series-3);
    --lk-feeds: var(--ink-soft);
    --lk-advances: var(--accent);
    --lk-works_on: #6250d6;
    --lk-learns: var(--danger);
  }
  @media (prefers-color-scheme: dark) {
    .pathways { --lane-supervision: #9085e9; --lk-works_on: #9085e9; }
  }

  .views { display: flex; gap: 0.25rem; margin-top: 0.6rem; font-family: var(--font-ui); }
  .views button { font-size: 0.88rem; padding: 0.35rem 0.85rem; }
  .views button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .toolbar { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.8rem 0 0.4rem; font-family: var(--font-ui); }
  .toolbar button { font-size: 0.85rem; padding: 0.35rem 0.7rem; }
  .spacer { flex: 1; }
  .years { display: flex; gap: 0.2rem; }
  .years button { font-size: 0.8rem; padding: 0.25rem 0.55rem; }
  .years button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .toggle { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.82rem; color: var(--ink-soft); }
  .toggle input { width: auto; }
  .legend { display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; align-items: center; font-family: var(--font-ui); font-size: 0.78rem; margin-bottom: 0.6rem; }
  .legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
  .legend .hint { flex-basis: 100%; }
  .lk { display: inline-block; width: 22px; height: 0; border-top: 2px solid; }
  .lk.feeds { border-color: var(--lk-feeds); }
  .lk.advances { border-color: var(--lk-advances); }
  .lk.works_on { border-color: var(--lk-works_on); }
  .lk.learns { border-color: var(--lk-learns); border-top-style: dashed; }
  .lk.funds { border-color: var(--lk-funds); border-top-style: dotted; }

  .scroller { overflow-x: auto; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); }
  .map { position: relative; font-family: var(--font-ui); user-select: none; touch-action: pan-y; }
  .map.dragging { cursor: grabbing; }
  .lane { position: absolute; left: 0; right: 0; border-top: 1px solid var(--rule); }
  .lane.alt { background: color-mix(in srgb, var(--panel) 55%, transparent); }
  .lane-label { position: absolute; left: 10px; top: 10px; font-size: 0.85rem; font-weight: 600; }
  .lane-research .lane-label { color: var(--lane-research); }
  .lane-teaching .lane-label { color: var(--lane-teaching); }
  .lane-outreach .lane-label { color: var(--lane-outreach); }
  .lane-supervision .lane-label { color: var(--lane-supervision); }
  .lane-grants .lane-label { color: var(--lane-grants); }
  .tick { position: absolute; top: 4px; border-left: 1px dotted var(--rule); pointer-events: none; }
  .tick.major { border-left-style: solid; }
  .tick span { position: absolute; left: 4px; top: 0; font-size: 0.72rem; color: var(--ink-soft); white-space: nowrap; }
  .now { position: absolute; top: 4px; border-left: 2px solid var(--accent); pointer-events: none; }
  .now span { position: absolute; left: 4px; top: 12px; font-size: 0.7rem; color: var(--accent); }
  .goals-head { position: absolute; top: 6px; font-size: 0.75rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.06em; }

  .links { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
  .lk-path { fill: none; stroke-width: 1.6; pointer-events: stroke; }
  .lk-path.feeds { stroke: var(--lk-feeds); }
  .lk-path.advances { stroke: var(--lk-advances); }
  .lk-path.works_on { stroke: var(--lk-works_on); }
  .lk-path.learns { stroke: var(--lk-learns); stroke-dasharray: 5 4; }
  /* funding is dotted while the grant is undecided, solid once awarded, faint if declined */
  .lk-path.funds { stroke: var(--lk-funds); stroke-dasharray: 2 4; }
  .lk-path.funds.awarded { stroke-dasharray: none; stroke-width: 2.2; }
  .lk-path.funds.declined { opacity: 0.3; }
  .lk-path.drawing { stroke: var(--accent); stroke-dasharray: 3 3; }
  .ah.feeds { fill: var(--lk-feeds); } .ah.advances { fill: var(--lk-advances); }
  .ah.works_on { fill: var(--lk-works_on); } .ah.learns { fill: var(--lk-learns); } .ah.funds { fill: var(--lk-funds); }

  .node {
    position: absolute; box-sizing: border-box; display: grid; align-content: center; gap: 1px;
    padding: 0.2rem 1.1rem 0.2rem 0.55rem; background: var(--paper); border: 1px solid var(--rule);
    border-left: 4px solid var(--lane-research); border-radius: 6px; cursor: grab; overflow: visible;
    box-shadow: 0 1px 2px rgb(0 0 0 / 0.06);
  }
  .node:hover { box-shadow: 0 0 0 1px var(--ink-soft); z-index: 3; }
  .node:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .node.moving { opacity: 0.85; z-index: 5; box-shadow: 0 6px 16px rgb(0 0 0 / 0.2); }
  .node.lane-teaching { border-left-color: var(--lane-teaching); }
  .node.lane-outreach { border-left-color: var(--lane-outreach); }
  .node.lane-supervision { border-left-color: var(--lane-supervision); }
  .node.lane-grants { border-left-color: var(--lane-grants); }
  .node.gs-drafting { border-style: dashed; border-left-style: solid; }
  .node.gs-awarded { border-width: 2px; border-left-width: 6px; background: color-mix(in srgb, var(--lane-grants) 10%, var(--paper)); }
  .node.gs-declined { opacity: 0.5; }
  .node.gs-declined .n-title { text-decoration: line-through; }
  .node.kind-goal { border-radius: 22px; border-width: 2px; border-left-width: 6px; font-weight: 600; }
  .node.kind-objective { background: color-mix(in srgb, var(--panel) 70%, var(--paper)); border-width: 2px; border-left-width: 6px; }
  .node.potential { border-style: dashed; border-left-style: dashed; background: transparent; }
  .node.kind-gap { border-style: dotted; border-left-style: solid; }
  .node.open-end { border-right-style: dashed; }
  .node.inactive { opacity: 0.5; }
  .n-title { font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .n-sub { font-size: 0.66rem; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 400; }
  .resize { position: absolute; right: -2px; top: 0; bottom: 0; width: 9px; cursor: ew-resize; }
  .connector {
    /* just outside the right edge, clear of the stretch strip */
    position: absolute; right: -21px; top: 50%; transform: translateY(-50%); width: 16px; height: 16px;
    display: grid; place-items: center; font-size: 0.75rem; line-height: 1; color: var(--accent);
    background: var(--paper); border-radius: 50%; cursor: crosshair; opacity: 0; transition: opacity 0.1s;
  }
  .node:hover .connector, .node:focus-visible .connector, .map.dragging .connector { opacity: 1; }

  dialog {
    width: min(48rem, calc(100vw - 32px)); max-height: calc(100vh - 32px);
    border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); color: var(--ink); padding: 1.1rem 1.2rem;
  }
  dialog::backdrop { background: rgb(0 0 0 / 0.35); }
  .small { font-size: 0.82rem; font-family: var(--font-ui); }
  .imp { display: grid; gap: 0.4rem; max-height: 55vh; overflow-y: auto; font-family: var(--font-ui); margin: 0.6rem 0; }
  .imp-group { border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.3rem 0.6rem; }
  .imp-group summary { cursor: pointer; font-size: 0.88rem; padding: 0.2rem 0; }
  .imp-row { display: flex; flex-wrap: wrap; gap: 0.2rem 0.6rem; align-items: baseline; padding: 0.3rem 0.2rem; font-size: 0.85rem; cursor: pointer; }
  .imp-row input { width: auto; }
  .imp-row.off { opacity: 0.55; cursor: default; }
  .imp-name { font-weight: 600; }
  .imp-row .muted { font-size: 0.78rem; }
  .imp-actions { display: flex; gap: 0.5rem; font-family: var(--font-ui); }
  dialog h2 { margin: 0 0 0.8rem; font-size: 1.1rem; }
</style>
