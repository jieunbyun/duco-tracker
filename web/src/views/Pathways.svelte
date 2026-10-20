<script lang="ts">
  import { loadProjects, loadTaxonomy, setProjectDates } from "../lib/data";
  import type { Project, Taxonomy } from "../lib/data";
  import { LIVE_STATUSES } from "../lib/plan";
  import { loadReadings } from "../lib/reading";
  import type { Reading } from "../lib/reading";
  import {
    LANES, NODE_KINDS, loadPathways, saveYears, saveNode, saveLink,
    monthStart, monthEnd, fmtMonth, addMonths, fraction, monthAt, monthsBetween, shiftMonths,
  } from "../lib/pathways";
  import type { PwNode, PwLink, PwNodeFields, NodeKind, Lane } from "../lib/pathways";
  import { today, fmtDay } from "../lib/dates";
  import PwEditor from "../lib/PwEditor.svelte";
  import InfoSystem from "../lib/InfoSystem.svelte";
  import PwList from "../lib/PwList.svelte";
  import AssetEditor from "../lib/AssetEditor.svelte";
  import { loadAssets } from "../lib/assets";
  import type { Asset } from "../lib/assets";
  import { loadGroupProjects, loadEntries } from "../lib/group";
  import type { GroupProject, Entry } from "../lib/group";

  // ---- data -----------------------------------------------------------------------
  let nodes = $state<PwNode[]>([]);
  let links = $state<PwLink[]>([]);
  let years = $state(5);
  let projects = $state<Project[]>([]);
  let tax = $state<Taxonomy | null>(null);
  let assets = $state<Asset[]>([]);
  let groupProjects = $state<GroupProject[]>([]);
  let groupEntries = $state<Entry[]>([]);

  // three views of the same pathways: the map, a list for entering and linking, and the information system
  type View = "map" | "list" | "system";
  const VIEW_KEY = "pathways.view";
  function savedView(): View {
    try {
      const v = localStorage.getItem(VIEW_KEY);
      return v === "system" || v === "list" ? v : "map";
    } catch { return "map"; }
  }
  let view = $state<View>(savedView());
  function setView(v: View) {
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
      // students' shared projects and their logbooks (none before 0015, or without a group)
      [groupProjects, groupEntries] = await Promise.all([
        loadGroupProjects().catch(() => [] as GroupProject[]), loadEntries().catch(() => [] as Entry[]),
      ]);
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
  const LABEL_W = 110, GOAL_W = 270, GOAL_R = 44, GAP = 18, AXIS_H = 30, ROW_H = 58, NODE_H = 44, PAD = 10, MIN_W = 96;
  // GOAL_R: room right of the goals column for the goals' ○ and for links that loop between two goals
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

  // A goal without dates sits in the goals column at the horizon; with dates it
  // sits on the timeline like anything else (an open-ended one runs to the horizon).
  const inColumn = (n: PwNode) => n.kind === "goal" && !n.start_on && !n.end_on;
  const endOf = (n: PwNode, s: string) => n.end_on ?? (n.kind === "goal" ? to : addMonths(monthStart(s), 3));

  // ---- dragging (move / stretch / link) -------------------------------------------
  type Drag =
    | { mode: "move" | "resize"; id: string; px: number; py: number; moved: boolean;
        dated: boolean; start: string; end: string | null; lane: Lane; row: number }
    | { mode: "link"; id: string; x: number; y: number };
  let drag = $state<Drag | null>(null);
  let mapEl = $state<HTMLDivElement | null>(null);

  /** A node as it should be drawn: with the drag applied, if it is the one moving. */
  function shown(n: PwNode): PwNode {
    if (drag && drag.mode !== "link" && drag.id === n.id && drag.moved) {
      return { ...n, start_on: drag.dated ? drag.start : null, end_on: drag.dated ? drag.end : null, lane: drag.lane, lane_row: drag.row };
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
    if (inColumn(n)) return { x: x1 + GAP, y, w: GOAL_W - GOAL_R, open: false };
    const s = n.start_on ?? today();
    const e = endOf(n, s);
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
      drag = { mode, id: n.id, px: p.x, py: p.y, moved: false, dated: !inColumn(n),
               start: s, end: n.kind === "goal" ? n.end_on : endOf(n, s), lane: n.lane, row: n.lane_row };
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  // Pathways works in months; a linked Planning project keeps its own days.
  const snapStart = (n: PwNode, iso: string) => (n.project_id ? iso : monthStart(iso));
  const snapEnd = (n: PwNode, iso: string) => (n.project_id ? iso : monthEnd(iso));

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
    const e0 = endOf(n, s0);
    const f = (x: number) => (x - x0) / (x1 - x0);
    if (drag.mode === "resize") {
      const k = monthsBetween(monthStart(e0), monthAt(f(xOf(e0) + dx), from, to));
      let end = snapEnd(n, shiftMonths(e0, k));
      if (end <= s0) end = snapEnd(n, shiftMonths(s0, 1));
      drag = { ...drag, moved: true, end };
    } else {
      const where = laneAt(p.y);
      if (n.kind === "goal" && p.x > x1) {
        // dropped in the goals column: no dates
        drag = { ...drag, moved: true, dated: false, lane: where.lane, row: where.row };
      } else if (inColumn(n)) {
        // from the goals column onto the timeline: starts where it is dropped, runs on
        drag = { ...drag, moved: true, dated: true, start: monthAt(f(Math.max(x0, p.x)), from, to), end: null, lane: where.lane, row: where.row };
      } else {
        const k = monthsBetween(monthStart(s0 < from ? from : s0), monthAt(f(xOf(s0 < from ? from : s0) + dx), from, to));
        const end = n.kind === "goal" && !n.end_on ? null : snapEnd(n, shiftMonths(e0, k));
        drag = { ...drag, moved: true, dated: true, start: snapStart(n, shiftMonths(s0, k)), end, lane: where.lane, row: where.row };
      }
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
          await saveLink(n.id, to.id);
          await load();
        }
        return;
      }
      if (!d.moved) return openEdit(raw!); // a click
      const fields: Partial<PwNodeFields> = { lane: d.lane, lane_row: d.row };
      Object.assign(fields, d.dated ? { start_on: d.start, end_on: d.end } : { start_on: null, end_on: null });
      // show it where it was dropped straight away; the reload confirms
      nodes = nodes.map((x) => (x.id === n.id ? { ...x, ...fields } as PwNode : x));
      if (n.project_id && n.kind !== "goal") {
        projects = projects.map((p) => (p.id === n.project_id ? { ...p, start_on: d.start, end_on: d.end } : p));
        await setProjectDates(n.project_id, d.start, d.end ?? n.end_on);
      }
      await saveNode(n.id, fields);
      await load();
    } catch (e) {
      error = (e as Error).message;
      await load();
    }
  }

  // ---- links drawn as curves --------------------------------------------------------
  // Each link leaves one side of a card and reaches a side of another:
  //  - cards in different rows that meet or overlap in time: bottom/top middle;
  //  - same row, one starting where the other ends: a hook under the join;
  //  - otherwise: from the right edge to the left edge (or round to the right
  //    edge, going back in time, and between goals in the column).
  // Where several links share a side of a card, their ends are spread along it,
  // in the order of where they come from, so they stay apart and do not cross.
  type Side = "top" | "bottom" | "left" | "right";
  type Route = { l: PwLink; a: Box; b: Box; hook: boolean; from: Side; to: Side };
  const drawnLinks = $derived.by(() => {
    const routes: Route[] = links
      .map((l) => ({ l, a: boxes.get(l.from_id), b: boxes.get(l.to_id) }))
      .filter((x): x is { l: PwLink; a: Box; b: Box } => !!x.a && !!x.b)
      .map(({ l, a, b }) => {
        const gap = b.x - (a.x + a.w);
        const bothGoalsColumn = a.x === x1 + GAP && b.x === x1 + GAP;
        if (gap < 40 && b.y !== a.y && !bothGoalsColumn) {
          const down = b.y > a.y;
          return { l, a, b, hook: false, from: down ? "bottom" : "top", to: down ? "top" : "bottom" } as Route;
        }
        if (gap >= -4 && gap < 40 && b.y === a.y) return { l, a, b, hook: true, from: "bottom", to: "bottom" } as Route;
        return { l, a, b, hook: false, from: "right", to: gap >= -4 ? "left" : "right" } as Route;
      });

    // spread the ends sharing a side of a card
    const cx = (x: Box) => x.x + x.w / 2, cy = (x: Box) => x.y + NODE_H / 2;
    const ends = new Map<string, { key: string; order: number }[]>();
    for (const r of routes) {
      if (r.hook) continue; // hooks sit at the ends of the cards, apart already
      for (const [id, side, other, end] of [[r.l.from_id, r.from, r.b, "from"], [r.l.to_id, r.to, r.a, "to"]] as const) {
        const k = `${id}:${side}`;
        const order = side === "top" || side === "bottom" ? cx(other) : cy(other);
        ends.set(k, [...(ends.get(k) ?? []), { key: `${r.l.id}:${end}`, order }]);
      }
    }
    const offset = new Map<string, number>();
    for (const [k, list] of ends) {
      const side = k.slice(k.lastIndexOf(":") + 1) as Side;
      const box = boxes.get(k.slice(0, k.lastIndexOf(":")))!;
      list.sort((p, q) => p.order - q.order);
      const n = list.length;
      const room = side === "top" || side === "bottom" ? box.w * 0.6 : NODE_H - 14;
      const step = n > 1 ? Math.min(side === "top" || side === "bottom" ? 22 : 8, room / (n - 1)) : 0;
      list.forEach((e, i) => offset.set(e.key, (i - (n - 1) / 2) * step));
    }
    const point = (x: Box, side: Side, o: number) =>
      side === "top" ? { x: cx(x) + o, y: x.y } : side === "bottom" ? { x: cx(x) + o, y: x.y + NODE_H }
      : side === "left" ? { x: x.x, y: cy(x) + o } : { x: x.x + x.w, y: cy(x) + o };

    return routes.map((r) => {
      const { l, a, b } = r;
      if (r.hook) {
        const hx1 = a.x + a.w - 14, hx2 = b.x + 14, y = a.y + NODE_H, bend = 15;
        return { l, d: `M ${hx1} ${y} C ${hx1} ${y + bend}, ${hx2} ${y + bend}, ${hx2} ${y}` };
      }
      const p = point(a, r.from, offset.get(`${l.id}:from`) ?? 0);
      const q = point(b, r.to, offset.get(`${l.id}:to`) ?? 0);
      if (r.from === "top" || r.from === "bottom") {
        const bend = Math.max(12, Math.abs(q.y - p.y) / 2) * (r.from === "bottom" ? 1 : -1);
        return { l, d: `M ${p.x} ${p.y} C ${p.x} ${p.y + bend}, ${q.x} ${q.y - bend}, ${q.x} ${q.y}` };
      }
      const forward = r.to === "left";
      const dx = Math.max(40, Math.abs(q.x - p.x) / 2) * (forward ? 1 : -1);
      return { l, d: `M ${p.x} ${p.y} C ${p.x + Math.abs(dx)} ${p.y}, ${q.x - dx} ${q.y}, ${q.x} ${q.y}` };
    });
  });
  const nodeTitle = (id: string) => nodes.find((x) => x.id === id)?.title ?? "";

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
    const inLane = [...visible, ...also].filter((n) => n.lane === lane && (kind === "goal") === inColumn(n));
    for (let row = 0; ; row++) {
      const clash = inLane.some((n) => n.lane_row === row && (kind === "goal" ||
        ((n.start_on ?? today()) <= e && endOf(n, n.start_on ?? today()) >= s)));
      if (!clash) return row;
    }
  }
  function openNew(kind: NodeKind) {
    const lane = (NODE_KINDS.find((k) => k.key === kind)?.lane ?? "research") as Lane;
    const s = monthStart(today());
    const e = monthEnd(addMonths(s, Math.max(1, DEFAULT_MONTHS[kind]) - 1));
    panel = {
      node: null,
      draft: {
        kind, lane, potential: kind === "project", grant_stage: kind === "grant" ? "drafting" : null,
        start_on: kind === "goal" ? null : s, end_on: kind === "goal" ? null : e,
        lane_row: freeRow(lane, kind, s, e),
      },
    };
  }
  /** Add an item straight from the list, with the same defaults as the + buttons. */
  async function quickAdd(kind: NodeKind, lane: Lane, title: string, start: string | null, end: string | null) {
    let s = start, e = end;
    if (kind !== "goal" && !s) s = monthStart(today());
    if (kind !== "goal" && !e && s) e = monthEnd(addMonths(monthStart(s), DEFAULT_MONTHS[kind] - 1));
    const inCol = kind === "goal" && !s && !e;
    const rs = s ?? today(), re = e ?? addMonths(monthStart(rs), 12);
    await saveNode(null, {
      kind, lane, title, potential: kind === "project", grant_stage: kind === "grant" ? "drafting" : null,
      start_on: s, end_on: e, lane_row: inCol ? freeRow(lane, "goal", rs, re) : freeRow(lane, kind === "goal" ? "project" : kind, rs, re),
    });
    await load();
  }

  // ---- bring existing Planning projects onto the map ------------------------------------
  // Each lands in its area's lane (research projects, students' included, go to
  // the Projects lane), keeps the project's dates, and stays linked to it.
  type ImportRow = { p: Project; group: string; lane: Lane; kind: "project" | "grant"; already: boolean; pick: boolean };
  let importRows = $state<ImportRow[]>([]);
  let importing = $state(false);

  function laneFor(p: Project): { lane: Lane; kind: "project" | "grant"; group: string } {
    const c = tax?.allCategories.find((x) => x.id === p.category_id);
    const a = tax?.areas.find((x) => x.id === c?.area_id);
    const group = `${a?.label ?? "Other"} › ${c?.label ?? "—"}`;
    if (c?.code === "RES_PROP") return { lane: "grants", kind: "grant", group };
    if (a?.code === "TEA") return { lane: "teaching", kind: "project", group };
    if (a?.code === "OUT") return { lane: "outreach", kind: "project", group };
    return { lane: "projects", kind: "project", group };
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
    const stages = links.map((l) => (l.to_id === id ? nodeById.get(l.from_id) : undefined))
      .filter((n) => n?.kind === "grant").map((n) => n!.grant_stage ?? "drafting");
    if (stages.includes("awarded")) return "funded";
    return stages.some((s) => s !== "declined") ? "funding pending" : null;
  }
  function sub(n: PwNode): string {
    const bits: string[] = [n.potential ? "potential project" : n.kind === "grant" ? `grant · ${n.grant_stage ?? "drafting"}` : kindLabel(n.kind).toLowerCase()];
    if (n.kind === "project" && n.hands_on) bits.unshift("hands-on");
    if (n.kind === "grant" && n.end_on) bits.push(`deadline ${fmtMonth(n.end_on)}`);
    else if (n.start_on) bits.push(`${fmtMonth(n.start_on)} → ${n.end_on ? fmtMonth(n.end_on) : "…"}`);
    else if (n.end_on) bits.push(`by ${fmtMonth(n.end_on)}`);
    if (n.kind === "grant" && n.cost) bits.push(n.cost.toLocaleString());
    const fu = funding(n.id);
    if (fu) bits.push(fu);
    if (n.effort_pm) bits.push(`${n.effort_pm} pm`);
    if (n.fte) bits.push(`${Math.round(n.fte * 100)}%`);
    if (n.group_project_id) {
      const since = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
      const k = groupEntries.filter((e) => e.project_id === n.group_project_id && e.entry_date >= since).length;
      bits.push(`logbook ${k} this week`);
    }
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
    <button role="tab" aria-selected={view === "list"} class:on={view === "list"} onclick={() => setView("list")}>List</button>
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
    {#if view === "map"}
      <div class="years" role="group" aria-label="How far ahead">
        {#each [3, 5, 10, 15, 20] as y (y)}
          <button class:on={years === y} aria-pressed={years === y} onclick={() => setYears(y)}>{y} yr</button>
        {/each}
      </div>
    {/if}
    <label class="toggle"><input type="checkbox" bind:checked={showAll} /> Show done and retired</label>
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{/if}

  {#if view === "list"}
    <PwList shown={visible} all={nodes.map(eff)} {links} {sub} onedit={openEdit} onadd={quickAdd} onchanged={load} />
  {:else}
  <div class="legend muted" aria-hidden="true">
    <span class="hint">Drag an item to move it in time or across lanes · drag its right edge to stretch it · drag its ○ onto another item to link them · click to edit</span>
  </div>

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
      <div class="goals-head" style:left={`${x1 + GAP}px`} style:width={`${GOAL_W - GOAL_R}px`}>Goals · by {fmtDay(to).replace(/^1 /, "")}</div>

      <!-- links -->
      <svg class="links" width={mapW} height={mapH} aria-hidden="true">
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" class="ah" />
          </marker>
        </defs>
        {#each drawnLinks as dl (dl.l.id)}
          <path d={dl.d} class="lk-path" marker-end="url(#arrow)">
            <title>{nodeTitle(dl.l.from_id)} → {nodeTitle(dl.l.to_id)}</title>
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
        <div class="node kind-{n.kind} lane-{n.lane} {n.kind === "grant" ? `gs-${n.grant_stage ?? "drafting"}` : ""}" class:potential={n.potential} class:hands-on={n.kind === "project" && n.hands_on} class:open-end={b.open}
             class:inactive={n.status !== "active"} class:moving={drag?.id === n.id}
             data-node={n.id} role="button" tabindex="0" title={`${n.title}${n.detail ? `\n${n.detail}` : ""}`}
             style:left={`${b.x}px`} style:top={`${b.y}px`} style:width={`${b.w}px`} style:height={`${NODE_H}px`}
             onpointerdown={(ev) => begin(ev, n, "move")}
             onkeydown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openEdit(n); } }}>
          <span class="n-title">{n.kind === "goal" ? "◎ " : n.kind === "gap" ? "? " : ""}{#if n.kind === "project" && n.hands_on}<span class="hand" title="Hands-on">✋</span>{/if}{n.title}</span>
          <span class="n-sub">{n.status !== "active" ? `${n.status} · ` : ""}{sub(n)}</span>
          {#if !inColumn(n)}
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
                {r.p.start_on || r.p.end_on ? `${r.p.start_on ? fmtMonth(r.p.start_on) : "…"} → ${r.p.end_on ? fmtMonth(r.p.end_on) : "…"}` : "no dates"}
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
      <PwEditor node={panel.node} draft={panel.draft} {nodes} {links} {projects} {readings} {groupProjects} onsaved={saved} oncancel={() => (panel = null)} />
    {/key}
  {/if}
</dialog>

<style>
  .pathways {
    --lane-research: var(--series-1);
    --lane-teaching: var(--series-2);
    --lane-outreach: var(--series-4);
    --lane-projects: #6250d6;
    --lane-grants: var(--series-3);
    --lk: var(--ink-soft);
  }
  @media (prefers-color-scheme: dark) {
    .pathways { --lane-projects: #9085e9; }
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

  .scroller { overflow-x: auto; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); }
  .map { position: relative; font-family: var(--font-ui); user-select: none; touch-action: pan-y; }
  .map.dragging { cursor: grabbing; }
  .lane { position: absolute; left: 0; right: 0; border-top: 1px solid var(--rule); }
  .lane.alt { background: color-mix(in srgb, var(--panel) 55%, transparent); }
  .lane-label { position: absolute; left: 10px; top: 10px; max-width: 92px; font-size: 0.85rem; font-weight: 600; line-height: 1.25; }
  .lane-research .lane-label { color: var(--lane-research); }
  .lane-teaching .lane-label { color: var(--lane-teaching); }
  .lane-outreach .lane-label { color: var(--lane-outreach); }
  .lane-projects .lane-label { color: var(--lane-projects); }
  .lane-grants .lane-label { color: var(--lane-grants); }
  .tick { position: absolute; top: 4px; border-left: 1px dotted var(--rule); pointer-events: none; }
  .tick.major { border-left-style: solid; }
  .tick span { position: absolute; left: 4px; top: 0; font-size: 0.72rem; color: var(--ink-soft); white-space: nowrap; }
  .now { position: absolute; top: 4px; border-left: 2px solid var(--accent); pointer-events: none; }
  .now span { position: absolute; left: 4px; top: 12px; font-size: 0.7rem; color: var(--accent); }
  .goals-head { position: absolute; top: 6px; font-size: 0.75rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.06em; }

  .links { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
  .lk-path { fill: none; stroke-width: 1.6; pointer-events: stroke; }
  .lk-path { stroke: var(--lk); }
  /* funding is dotted while the grant is undecided, solid once awarded, faint if declined */
  .lk-path.drawing { stroke: var(--accent); stroke-dasharray: 3 3; }
  .ah { fill: var(--lk); }

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
  .node.lane-projects { border-left-color: var(--lane-projects); }
  /* hands-on: your own research time goes into it */
  .node.hands-on { border-width: 2px; border-left-width: 7px; background: color-mix(in srgb, var(--accent) 9%, var(--paper)); }
  .node.hands-on .n-title { font-weight: 700; }
  .hand { margin-right: 0.25rem; }
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
