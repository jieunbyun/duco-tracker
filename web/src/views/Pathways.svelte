<script lang="ts">
  import { loadProjects, loadTaxonomy, setProjectDates, setMilestoneDates, loadAllHours } from "../lib/data";
  import type { Project, Milestone, Taxonomy, HourRow } from "../lib/data";
  import ProjectEditor from "../lib/ProjectEditor.svelte";
  import Milestones from "../lib/Milestones.svelte";
  import PwExperiments from "../lib/PwExperiments.svelte";
  import { loadExperiments } from "../lib/experiments";
  import type { Topic, Note as ExpNote } from "../lib/experiments";
  import type { GroupMilestone } from "../lib/group";
  import { LIVE_STATUSES, milestoneDates } from "../lib/plan";
  import { loadReadings } from "../lib/reading";
  import type { Reading } from "../lib/reading";
  import {
    LANES, NODE_KINDS, staged, loadPathways, loadMemberMap, loadContributors, saveYears, saveNode, saveLink,
    monthStart, monthEnd, fmtMonth, addMonths, fraction, monthAt, monthsBetween, shiftMonths,
    isAmbition, ambitionsIn, ambitionsVia, loadExpLinks, loadAmbLinks, setAmbitions,
  } from "../lib/pathways";
  import type { PwNode, PwLink, PwNodeFields, NodeKind, Lane, PwAmbLink } from "../lib/pathways";
  import PwCoverage from "../lib/PwCoverage.svelte";
  import { today, fmtDay } from "../lib/dates";
  import PwEditor from "../lib/PwEditor.svelte";
  import OutputsMap from "../lib/OutputsMap.svelte";
  import PwList from "../lib/PwList.svelte";
  import { loadOutputs } from "../lib/assets";
  import FolderLink from "../lib/FolderLink.svelte";
  import { undoable } from "../lib/undo.svelte";
  import { preview } from "../lib/preview.svelte";
  import type { Output, OutputLink } from "../lib/assets";
  import { loadGroupProjects, loadMembers, myId, loadMilestones as loadSharedMilestones } from "../lib/group";
  import type { GroupProject, Member } from "../lib/group";
  import { loadProjectActivity } from "../lib/actions";
  import { arrivedAt } from "../lib/dayBack.svelte";

  // A member sees a read-only chart: the items they contribute to, and the goals they lead to.
  let { member = false }: { member?: boolean } = $props();

  // ---- data -----------------------------------------------------------------------
  let nodes = $state<PwNode[]>([]);
  let links = $state<PwLink[]>([]);
  let years = $state(5);
  let projects = $state<Project[]>([]);
  let tax = $state<Taxonomy | null>(null);
  // the group's outputs (the second view): what has been developed, by whom, linked to publications
  let outputs = $state<Output[]>([]);
  let outputLinks = $state<OutputLink[]>([]);
  let outputTitles = $state(new Map<string, string>());
  let me = $state("");
  let groupProjects = $state<GroupProject[]>([]);
  let groupActivity = $state(new Map<string, number>()); // comments on each shared project's actions this week
  let groupMembers = $state<Member[]>([]);
  let contributors = $state(new Map<string, string[]>());
  // to change a linked project's Planning side, and an item's Experiments, without leaving the map
  let expTopics = $state<Topic[]>([]);
  let expNotes = $state<ExpNote[]>([]);
  let expLinks = $state<{ node_id: string; topic_id: string }[] | null>(null); // null before 0076 is run
  let sharedMilestones = $state<GroupMilestone[]>([]);
  let ambLinks = $state<PwAmbLink[] | null>(null); // the ambitions ticked for each item; null before 0080 is run
  let hours = $state<HourRow[]>([]); // logged, for the milestones' hours: read when first needed
  let hoursRead = false;
  function readHours() {
    if (hoursRead) return;
    hoursRead = true;
    loadAllHours().then((h) => (hours = h)).catch(() => (hoursRead = false));
  }
  async function loadExp() {
    const [e, l] = await Promise.all([
      loadExperiments().catch(() => ({ topics: [] as Topic[], notes: [] as ExpNote[] })), // none before 0066
      loadExpLinks().catch(() => null),
    ]);
    [expTopics, expNotes, expLinks] = [e.topics, e.notes, l];
  }

  // four views of the same pathways: the ambitions and what serves each, the map, a list for entering
  // and linking, and the information system
  type View = "ambitions" | "map" | "list" | "system";
  const VIEW_KEY = "pathways.view";
  function savedView(): View {
    if (member) return "map";
    try {
      const v = localStorage.getItem(VIEW_KEY);
      return v === "system" || v === "list" || v === "map" ? v : "ambitions";
    } catch { return "ambitions"; }
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
    if (member) {
      try {
        const as = preview.as?.user_id;
        const [mm, out, gm, id] = await Promise.all([loadMemberMap(as), loadOutputs(), loadMembers().catch(() => [] as Member[]), myId()]);
        ({ nodes, links } = mm);
        ({ outputs, links: outputLinks, titles: outputTitles } = out);
        [groupMembers, me] = [gm, as ?? id];
        error = "";
      } catch (e) {
        error = (e as Error).message;
      } finally {
        loading = false;
      }
      return;
    }
    try {
      const [pw, p, r, t, out, id] = await Promise.all([
        loadPathways(), loadProjects(), loadReadings().catch(() => [] as Reading[]), loadTaxonomy(),
        loadOutputs(), myId(), // no outputs before 0018 is run
      ]);
      tax = t;
      ({ outputs, links: outputLinks, titles: outputTitles } = out);
      me = id;
      // students' shared projects and their logbooks (none before 0015, or without a group)
      [groupProjects, groupActivity, groupMembers, contributors, , sharedMilestones, ambLinks] = await Promise.all([
        // (with any in the bin: saving an item must not unlink it)
        loadGroupProjects(true).catch(() => [] as GroupProject[]),
        loadProjectActivity(new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10)),
        loadMembers().catch(() => [] as Member[]), loadContributors(),
        loadExp(), loadSharedMilestones().catch(() => [] as GroupMilestone[]), loadAmbLinks().catch(() => null),
      ]);
      if (hoursRead) loadAllHours().then((h) => (hours = h)).catch(() => {});
      nodes = pw.nodes;
      links = pw.links;
      years = pw.years;
      projects = p;
      readings = r;
      const goal = arrived?.get("g");
      if (goal && arrived) arrived.delete("g");
      const n = nodes.find((x) => x.id === goal);
      if (n) openEdit(n);
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  // from the Day tab (#/pathways?g=<goal>): that goal open, with its thoughts
  const arrived = location.hash.startsWith("#/pathways") ? arrivedAt("pathways") : null; // (not a member's chart)
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
  // the goals column, only while a goal is on the map (ambitions are in the Ambitions view; a member's chart has them)
  const hasCol = $derived(member || nodes.some((n) => n.kind === "goal" && !isAmbition(n)));
  const x1 = $derived(mapW - (hasCol ? GOAL_W + GAP : 30));
  const from = $derived(monthStart(today()));
  const to = $derived(addMonths(from, years * 12));
  const xOf = (iso: string) => x0 + Math.min(1, Math.max(0, fraction(iso, from, to))) * (x1 - x0);

  // An item linked to a Planning project shows that project's current name and
  // dates (and is done once the project is); moving it moves the project.
  const projById = $derived(new Map(projects.map((p) => [p.id, p])));
  function eff(n: PwNode): PwNode {
    const p = n.project_id ? projById.get(n.project_id) : undefined;
    if (!p) return n;
    if (n.milestone_id) {
      // one of its milestones (0077): the milestone's name and dates, as Planning works them out
      const m = p.milestone.find((x) => x.id === n.milestone_id);
      if (!m) return n;
      const d = milestoneDates(p, m);
      return {
        ...n, title: m.title, folder_url: n.folder_url ?? p.folder_url,
        start_on: d.start ?? n.start_on, end_on: d.due ?? n.end_on,
        status: m.status !== "active" || p.status === "done" || p.status === "dropped" ? "done" : n.status,
      };
    }
    return {
      ...n,
      title: p.name,
      folder_url: n.folder_url ?? p.folder_url,
      start_on: p.start_on ?? n.start_on,
      end_on: p.end_on ?? n.end_on,
      status: p.status === "done" || p.status === "dropped" ? "done" : n.status,
    };
  }
  const visible = $derived(nodes.map(eff).filter((n) => showAll || n.status === "active"));

  // ---- ambitions: the few big goals; an item serves any of them (ticked, or where its links lead) ----
  const allAmbs = $derived(ambitionsIn(nodes)); // in your order
  const ambsByAge = $derived(nodes.filter(isAmbition)); // colours: by when each was made, so they stay put
  const shownAmbs = $derived(allAmbs.map(eff).filter((a) => visible.some((v) => v.id === a.id)));
  const AMB_COLOURS = 4;
  function ambColour(id: string | null): string | null {
    const i = id ? ambsByAge.findIndex((a) => a.id === id) : -1;
    return i < 0 ? null : i < AMB_COLOURS ? `var(--amb-${i + 1})` : "var(--ink-soft)";
  }
  const ambIds = $derived(new Set(ambsByAge.map((a) => a.id)));
  /** The ticks by item (before 0080: each item's one ambition so far). */
  const ambTicks = $derived.by(() => {
    const rows = ambLinks ?? nodes.filter((n) => n.kind !== "goal" && n.ambition_id).map((n) => ({ node_id: n.id, ambition_id: n.ambition_id! }));
    const m = new Map<string, string[]>();
    const order = (id: string) => allAmbs.findIndex((a) => a.id === id);
    for (const r of rows) if (ambIds.has(r.ambition_id)) m.set(r.node_id, [...(m.get(r.node_id) ?? []), r.ambition_id]);
    for (const [k, v] of m) m.set(k, v.sort((a, b) => order(a) - order(b)));
    return m;
  });
  const ambVia = $derived(ambitionsVia(nodes, links, ambTicks));
  /** The ambitions an item serves, in your order: ticked, else where its links lead (via). */
  function servesOf(id: string): { ids: string[]; via: boolean } {
    const t = ambTicks.get(id);
    return t?.length ? { ids: t, via: false } : { ids: ambVia.get(id) ?? [], via: true };
  }
  /** A cell of the Ambitions view clicked: with no ticks yet, those its links lead to are ticked with it. */
  async function tick(nodeId: string, amb: string) {
    if (!ambLinks) return (error = sqlHint("pw_node_ambition"));
    const had = ambTicks.get(nodeId) ?? [];
    const base = had.length ? had : ambVia.get(nodeId) ?? [];
    const want = had.length ? (had.includes(amb) ? had.filter((a) => a !== amb) : [...had, amb]) : base.includes(amb) ? base : [...base, amb];
    const on = want.includes(amb);
    const what = eff(nodes.find((x) => x.id === nodeId) ?? ({ title: "" } as PwNode)).title;
    // at once; the reload confirms
    ambLinks = [...ambLinks.filter((l) => l.node_id !== nodeId), ...want.map((a) => ({ node_id: nodeId, ambition_id: a }))];
    try {
      await undoable(on ? `Ticked “${ambTitle(amb)}” for “${what}”` : `Unticked “${ambTitle(amb)}” for “${what}”`,
        () => setAmbitions(nodeId, want, had));
      ambLinks = await loadAmbLinks();
    } catch (e) {
      const msg = (e as Error).message;
      ambLinks = await loadAmbLinks().catch(() => null);
      error = sqlHint(msg);
    }
  }
  const ambTitle = (id: string) => eff(nodes.find((x) => x.id === id) ?? ({ title: "" } as PwNode)).title;
  const covAmbitions = $derived(allAmbs.map(eff).map((a) => ({
    id: a.id, title: a.title, detail: a.detail, active: a.status === "active", colour: ambColour(a.id) ?? "var(--ink-soft)",
  })));
  const covItems = $derived(nodes.filter((n) => !isAmbition(n)).map(eff));

  // one ambition brought forward on the map, the rest faded — remembered on this computer
  const FOCUS_KEY = "pathways.focus";
  function stored(k: string): string | null {
    try { return localStorage.getItem(k); } catch { return null; }
  }
  function store(k: string, v: string | null) {
    try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch {}
  }
  let focus = $state<string | null>(stored(FOCUS_KEY)); // an ambition's id, or "none"
  function setFocus(f: string) { focus = focus === f ? null : f; store(FOCUS_KEY, focus); }

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
  // the ambitions themselves are in the Ambitions view, not on the map (a member's chart keeps its goals)
  const mapNodes = $derived(member ? visible : visible.filter((n) => !isAmbition(n)));
  const drawn = $derived(mapNodes.map(shown));

  const focusOn = $derived(focus === "none" || shownAmbs.some((a) => a.id === focus) ? focus : null);
  const fadedIds = $derived(new Set(focusOn === null ? [] : drawn.filter((n) => {
    const a = servesOf(n.id).ids;
    return focusOn === "none" ? a.length > 0 : !a.includes(focusOn);
  }).map((n) => n.id)));

  // ---- rows: a band per lane -------------------------------------------------------------
  type Span = { x: number; w: number; open: boolean };
  function span(n: PwNode): Span {
    if (inColumn(n)) return { x: x1 + GAP, w: GOAL_W - GOAL_R, open: false };
    const s = n.start_on ?? today();
    const e = endOf(n, s);
    const left = xOf(s < from ? from : s);
    const right = xOf(e > to ? to : e);
    return { x: left, w: Math.max(MIN_W, right - left), open: !n.end_on };
  }
  type Band = { key: string; lane: Lane; top: number; rows: number };
  const layout = $derived.by(() => {
    const bands: Band[] = [];
    let y = AXIS_H;
    // your own rows in each lane, with an empty one below to drag into
    for (const l of LANES) {
      const rows = Math.max(0, ...drawn.filter((n) => n.lane === l.key).map((n) => n.lane_row)) + 2;
      bands.push({ key: l.key, lane: l.key, top: y, rows });
      y += rows * ROW_H + 2 * PAD;
    }
    return { bands, height: y + 8 };
  });
  const bandByKey = $derived(new Map(layout.bands.map((b) => [b.key, b])));
  const mapH = $derived(layout.height);

  type Box = { x: number; y: number; w: number; open: boolean };
  function box(n: PwNode): Box {
    const b = bandByKey.get(n.lane);
    return { ...span(n), y: (b?.top ?? AXIS_H) + PAD + n.lane_row * ROW_H };
  }
  const boxes = $derived(new Map(drawn.map((n) => [n.id, box(n)])));

  function local(ev: PointerEvent) {
    const r = mapEl!.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  }
  /** The band under a point: its lane and the row in it. */
  function bandAt(y: number): { lane: Lane; row: number } {
    let b = layout.bands[0];
    for (const x of layout.bands) if (y >= x.top) b = x;
    if (!b) return { lane: "goals", row: 0 };
    return { lane: b.lane, row: Math.max(0, Math.min(b.rows - 1, Math.floor((y - b.top - PAD) / ROW_H))) };
  }

  function begin(ev: PointerEvent, n: PwNode, mode: "move" | "resize" | "link") {
    if (ev.button !== 0 || member) return;
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

  const DEAD_X = 30; // px a block must move sideways before its dates change

  // ---- tidy rows: close the empty lines in every row, keeping the order -------------
  // Goals in the column and items on the timeline sit side by side, so each is
  // tidied on its own; hidden (done, retired) items too, so nothing overlaps later.
  let tidying = $state(false);
  async function tidyRows() {
    const moves: { id: string; row: number }[] = [];
    for (const l of LANES) {
      for (const col of [true, false]) {
        const here = nodes.filter((n) => n.lane === l.key && inColumn(eff(n)) === col);
        const used = [...new Set(here.map((n) => n.lane_row))].sort((a, b) => a - b);
        for (const n of here) {
          const row = used.indexOf(n.lane_row);
          if (row !== n.lane_row) moves.push({ id: n.id, row });
        }
      }
    }
    if (!moves.length) return;
    tidying = true;
    try {
      await undoable("Tidied the rows", async () => {
        for (const m of moves) await saveNode(m.id, { lane_row: m.row });
      });
      await load();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      tidying = false;
    }
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
    const e0 = endOf(n, s0);
    const f = (x: number) => (x - x0) / (x1 - x0);
    if (drag.mode === "resize") {
      const k = monthsBetween(monthStart(e0), monthAt(f(xOf(e0) + dx), from, to));
      let end = snapEnd(n, shiftMonths(e0, k));
      if (end <= s0) end = snapEnd(n, shiftMonths(s0, 1));
      drag = { ...drag, moved: true, end };
    } else {
      const where = bandAt(p.y);
      if (n.kind === "goal" && p.x > x1) {
        // dropped in the goals column: no dates
        drag = { ...drag, moved: true, dated: false, lane: where.lane, row: where.row };
      } else if (inColumn(n)) {
        // from the goals column onto the timeline: starts where it is dropped, runs on
        drag = { ...drag, moved: true, dated: true, start: monthAt(f(Math.max(x0, p.x)), from, to), end: null, lane: where.lane, row: where.row };
      } else {
        // sideways moves need to be meant: nothing changes within the dead zone (or with Shift held),
        // so moving a block between rows or lanes does not nudge its dates
        const dxt = ev.shiftKey || Math.abs(dx) <= DEAD_X ? 0 : dx - Math.sign(dx) * DEAD_X;
        const k = monthsBetween(monthStart(s0 < from ? from : s0), monthAt(f(xOf(s0 < from ? from : s0) + dxt), from, to));
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
      if (n.milestone_id && n.project_id) {
        // stretching moves only its due date, so a start it takes from elsewhere stays so
        const md = d.mode === "resize" ? { due_on: d.end } : { start_on: d.start, due_on: d.end ?? n.end_on };
        projects = projects.map((p) => (p.id === n.project_id
          ? { ...p, milestone: p.milestone.map((m) => (m.id === n.milestone_id ? { ...m, ...md } : m)) } : p));
        await setMilestoneDates(n.milestone_id, md);
      } else if (n.project_id && n.kind !== "goal") {
        projects = projects.map((p) => (p.id === n.project_id ? { ...p, start_on: d.start, end_on: d.end } : p));
        await setProjectDates(n.project_id, d.start, d.end ?? n.end_on);
      }
      await saveNode(n.id, fields);
      await load();
    } catch (e) {
      const msg = (e as Error).message;
      await load(); // back as it was (this clears the message, so it is set after)
      error = sqlHint(msg);
    }
  }
  /** What to run when a newer column is missing; otherwise the message as it is. */
  function sqlHint(msg: string): string {
    const need = /milestone_id/.test(msg) ? ["Milestones on the map need", "0077_pw_milestone.sql"]
      : /ambition_order/.test(msg) ? ["Ordering the ambitions needs", "0078_pw_ambition_order.sql"]
      : /pw_node_ambition/.test(msg) ? ["Ticking an item for its ambitions needs", "0080_pw_node_ambition.sql"]
      : /ambition_id/.test(msg) ? ["Ambitions need", "0075_pw_ambition.sql"] : null;
    return need ? `${need[0]} web/db/${need[1]} run first, in the Supabase SQL editor.` : msg;
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
  // an item (or a new one, with the ambitions it serves), the projects from Planning, or what to add for an ambition
  type Panel = { node: PwNode | null; draft?: Partial<PwNodeFields>; serves?: string[] } | { importing: true }
    | { adding: { lane: Lane; amb: string } };
  let panel = $state<Panel | null>(null);
  /** How many of the group's outputs name this item as their publication. */
  const outputCount = (id: string) => outputs.filter((o) => o.status !== "retired" && o.publications.includes(id)).length;
  // what an output can name as its publication: the items in Publications & code/database
  const publicationOptions = $derived(
    nodes.map(eff).filter((n) => n.lane === "publications" && n.kind !== "person").map((n) => ({ id: n.id, title: n.title }))
      .sort((a, b) => a.title.localeCompare(b.title)),
  );
  let dialog = $state<HTMLDialogElement | null>(null);
  $effect(() => {
    if (!dialog) return;
    if (panel && !dialog.open) dialog.showModal();
    if (!panel && dialog.open) dialog.close();
  });

  function openEdit(n: PwNode) { panel = { node: n }; sheetTab = "item"; }

  const DEFAULT_MONTHS: Record<NodeKind, number> = { goal: 0, objective: 12, project: 12, person: 3 * 12, gap: 6, grant: 3, award: 3 };
  /** Whether a row in a lane is free over a span (goals: in the goals column), but for `except`. */
  function rowFree(lane: Lane, kind: NodeKind, s: string, e: string, row: number, except?: string, also: PwNode[] = []): boolean {
    return ![...mapNodes, ...also].some((n) => n.id !== except && n.lane === lane && (kind === "goal") === inColumn(n)
      && n.lane_row === row && (kind === "goal" || ((n.start_on ?? today()) <= e && endOf(n, n.start_on ?? today()) >= s)));
  }
  /** The first row in a lane free over a span (goals: the first free row in the goals column). */
  function freeRow(lane: Lane, kind: NodeKind, s: string, e: string, also: PwNode[] = [], except?: string): number {
    for (let row = 0; ; row++) if (rowFree(lane, kind, s, e, row, except, also)) return row;
  }
  function openNew(kind: NodeKind, inLane?: Lane, amb?: string) {
    const lane = inLane ?? (NODE_KINDS.find((k) => k.key === kind)?.lane ?? "goals") as Lane;
    const s = monthStart(today());
    const e = monthEnd(addMonths(s, Math.max(1, DEFAULT_MONTHS[kind]) - 1));
    panel = {
      node: null,
      draft: {
        kind, lane, potential: kind === "project", grant_stage: staged(kind) ? "drafting" : null,
        start_on: kind === "goal" ? null : s, end_on: kind === "goal" ? null : e,
        lane_row: freeRow(lane, kind, s, e),
      },
      // for an ambition's gap, or (on the map) with an ambition brought forward, a new item serves it
      serves: kind === "goal" ? [] : amb ? [amb] : view === "map" && focusOn && focusOn !== "none" ? [focusOn] : [],
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
      kind, lane, title, potential: kind === "project", grant_stage: staged(kind) ? "drafting" : null,
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
  let importMilestones = $state(true); // show the imported projects' milestones on their bars
  let importFind = $state(""); // a project's (or milestone's) name: its milestones can be ticked too
  let importMs = $state<Record<string, boolean>>({}); // milestones ticked

  function laneFor(p: Project): { lane: Lane; kind: "project" | "grant"; group: string } {
    const c = tax?.allCategories.find((x) => x.id === p.category_id);
    const a = tax?.areas.find((x) => x.id === c?.area_id);
    const group = `${a?.label ?? "Other"} › ${c?.label ?? "—"}`;
    if (c?.code === "RES_PROP") return { lane: "grants", kind: "grant", group };
    if (a?.code === "TEA") return { lane: "teaching", kind: "project", group };
    if (a?.code === "OUT") return { lane: "outreach", kind: "project", group };
    return { lane: "publications", kind: "project", group };
  }
  function openImport() {
    importFind = "";
    importMs = {};
    importRows = projects
      .filter((p) => LIVE_STATUSES.has(p.status))
      .map((p) => ({ p, ...laneFor(p), already: onMap.has(p.id), pick: false }))
      .sort((a, b) => a.group.localeCompare(b.group) || a.p.name.localeCompare(b.p.name));
    panel = { importing: true };
  }
  /** The projects whose name (or a milestone's) matches, each with its open milestones while searching. */
  const importShown = $derived.by(() => {
    const q = importFind.trim().toLocaleLowerCase();
    return importRows.map((r) => {
      const hit = !q || r.p.name.toLocaleLowerCase().includes(q);
      const ms = q ? r.p.milestone.filter((m) => m.status === "active" && (hit || m.title.toLocaleLowerCase().includes(q))) : [];
      return { r, ms, show: hit || ms.length > 0 };
    }).filter((x) => x.show);
  });
  const importGroups = $derived(
    [...new Set(importShown.map((x) => x.r.group))].map((g) => ({ group: g, rows: importShown.filter((x) => x.r.group === g) })),
  );
  const importCount = $derived(importRows.filter((r) => r.pick && !r.already).length
    + Object.entries(importMs).filter(([id, on]) => on && !msOnMap.has(id)).length);
  async function addImported() {
    importing = true;
    const placed: PwNode[] = [];
    try {
      const picks: { p: Project; m: Milestone | null }[] = [
        ...importRows.filter((x) => x.pick && !x.already).map((x) => ({ p: x.p, m: null })),
        ...projects.flatMap((p) => p.milestone.filter((m) => importMs[m.id] && !msOnMap.has(m.id)).map((m) => ({ p, m }))),
      ];
      for (const { p, m } of picks) {
        const fields = fieldsFor(p, m, undefined, placed);
        if (!m) fields.show_milestones = importMilestones && p.milestone.length > 0;
        const id = await saveNode(null, fields);
        const amb = focusAmb();
        if (amb && ambLinks) await setAmbitions(id, [amb], []);
        placed.push({ ...(fields as PwNode), id });
      }
    } catch (e) {
      error = sqlHint((e as Error).message);
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

  // ---- the side sheet: an item, its Experiments, and (linked to Planning) its project ----------
  type SheetTab = "item" | "planning" | "experiments";
  let sheetTab = $state<SheetTab>("item");
  function setSheetTab(t: SheetTab) {
    sheetTab = t;
    if (t === "planning") readHours();
  }
  /** The item open in the sheet, as it is now (the sheet stays open while things reload). */
  const cur = $derived.by(() => {
    if (!panel || !("node" in panel) || !panel.node) return null;
    const id = panel.node.id;
    const n = nodes.find((x) => x.id === id);
    return n ? eff(n) : null;
  });
  const curProject = $derived(cur?.project_id ? projById.get(cur.project_id) : undefined);
  const privateShared = $derived(new Map(sharedMilestones.map((m) => [m.id, m.is_private])));
  const actualByMilestone = $derived.by(() => {
    const m = new Map<string, number>();
    for (const h of hours) if (h.milestone_id) m.set(h.milestone_id, (m.get(h.milestone_id) ?? 0) + h.hours);
    return m;
  });
  const editorCategories = $derived(
    (tax?.categories ?? []).map((c) => ({ category: c, areaLabel: tax!.areas.find((a) => a.id === c.area_id)?.label ?? "" })),
  );
  // as in Planning: one in the bin stays listed while it is linked, so saving does not unlink it
  const sharedChoices = $derived(groupProjects.map((g) => ({
    id: g.id, title: g.title, taken: projects.some((p) => p.group_project_id === g.id), binned: !!g.deleted_at,
  })).filter((g) => g.taken || !g.binned));

  /** The Experiments topics on an item, in the order they were linked. */
  const expOf = (id: string) => (expLinks ?? []).filter((l) => l.node_id === id).map((l) => l.topic_id)
    .filter((t) => expTopics.some((x) => x.id === t));

  // ---- the tray: what is not on the map yet, to drag onto it ---------------------------------
  // a project is on the map as a whole; its milestones each on their own
  const onMap = $derived(new Set(nodes.filter((n) => !n.milestone_id).map((n) => n.project_id).filter(Boolean)));
  const msOnMap = $derived(new Set(nodes.map((n) => n.milestone_id).filter(Boolean)));
  const liveProjects = $derived(projects.filter((p) => LIVE_STATUSES.has(p.status)));
  const trayProjects = $derived(liveProjects.filter((p) => !onMap.has(p.id)));
  let trayFind = $state("");
  /** Searching: the projects whose name matches, with their open milestones off the map (or the milestones that match). */
  const trayFound = $derived.by(() => {
    const q = trayFind.trim().toLocaleLowerCase();
    if (!q) return null;
    return liveProjects.map((p) => {
      const hit = p.name.toLocaleLowerCase().includes(q);
      const ms = p.milestone.filter((m) => m.status === "active" && !msOnMap.has(m.id) && (hit || m.title.toLocaleLowerCase().includes(q)));
      return { p, ms, hit };
    }).filter((x) => x.hit || x.ms.length);
  });
  const TRAY_KEY = "pathways.tray";
  let trayOpen = $state(stored(TRAY_KEY) !== "closed");
  $effect(() => store(TRAY_KEY, trayOpen ? null : "closed"));
  const short = (s: string, k = 48) => (s.length > k ? `${s.slice(0, k)}…` : s);

  type TrayDrag = { kind: "project" | "milestone"; id: string; label: string; x: number; y: number; moved: boolean };
  let trayDrag = $state<TrayDrag | null>(null);
  function trayStart(ev: PointerEvent, kind: TrayDrag["kind"], id: string, label: string) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    trayDrag = { kind, id, label, x: ev.clientX, y: ev.clientY, moved: false };
    window.addEventListener("pointermove", trayMove);
    window.addEventListener("pointerup", trayUp);
    window.addEventListener("pointercancel", trayUp);
  }
  function trayMove(ev: PointerEvent) {
    if (trayDrag) trayDrag = { ...trayDrag, x: ev.clientX, y: ev.clientY, moved: true };
  }
  async function trayUp(ev: PointerEvent) {
    window.removeEventListener("pointermove", trayMove);
    window.removeEventListener("pointerup", trayUp);
    window.removeEventListener("pointercancel", trayUp);
    const d = trayDrag;
    trayDrag = null;
    if (!d?.moved || !mapEl || ev.type === "pointercancel") return;
    const r = mapEl.getBoundingClientRect();
    if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) return;
    const where = bandAt(ev.clientY - r.top);
    if (d.kind === "milestone") {
      const p = projects.find((x) => x.milestone.some((m) => m.id === d.id));
      const m = p?.milestone.find((x) => x.id === d.id);
      if (p && m) await placeProject(p, where, m);
      return;
    }
    const p = projects.find((x) => x.id === d.id);
    if (p) await placeProject(p, where);
  }
  /**
   * A Planning project, or one of its milestones (m), as a new item: in the lane it is dropped in, else
   * its area's lane; with its dates, linked to it.
   */
  function fieldsFor(p: Project, m: Milestone | null, where?: { lane: Lane }, also: PwNode[] = []): Partial<PwNodeFields> {
    const lane = !where || where.lane === "goals" ? laneFor(p).lane : where.lane;
    const kind = lane === "grants" ? "grant" : "project";
    const d = m ? milestoneDates(p, m) : { start: p.start_on, due: p.end_on };
    const s = d.start ?? monthStart(today());
    const e = d.due && d.due >= s ? d.due : null;
    return {
      kind, lane, title: m ? m.title : p.name, project_id: p.id, ...(m ? { milestone_id: m.id } : {}),
      potential: false, grant_stage: kind === "grant" ? "drafting" : null,
      start_on: s, end_on: e, lane_row: freeRow(lane, kind, s, e ?? addMonths(s, 3), also),
      show_milestones: !m && p.milestone.length > 0,
    };
  }
  /** The ambition a new item serves, on the map: the one brought forward. */
  const focusAmb = () => (focusOn && focusOn !== "none" ? focusOn : null);
  async function placeProject(p: Project, where?: { lane: Lane }, m: Milestone | null = null, amb: string | null = focusAmb()) {
    const fields = fieldsFor(p, m, where);
    try {
      await undoable(m ? `Put “${m.title}” (${p.name}) on Pathways` : `Put “${p.name}” on Pathways`, async () => {
        const id = await saveNode(null, fields);
        if (amb && ambLinks) await setAmbitions(id, [amb], []);
      });
      await load();
    } catch (e) {
      const msg = (e as Error).message;
      await load();
      error = sqlHint(msg);
    }
  }

  // ---- your order of the ambitions: drag a column's ⠿ in the Ambitions view --------------------
  /** The ambitions shown, in a new order; hidden ones (done, retired) keep their places. */
  async function reorderAmbitions(shownIds: string[]) {
    const moved = new Set(shownIds);
    if (shownIds.join() === allAmbs.filter((a) => moved.has(a.id)).map((a) => a.id).join()) return;
    let k = 0;
    const all = allAmbs.map((a) => (moved.has(a.id) ? shownIds[k++] : a.id));
    const was = new Map(nodes.map((n) => [n.id, n.ambition_order]));
    nodes = nodes.map((n) => (all.includes(n.id) ? { ...n, ambition_order: (all.indexOf(n.id) + 1) * 10 } : n)); // at once
    try {
      await undoable("Reordered the ambitions", async () => {
        for (const [i, id] of all.entries()) if (was.get(id) !== (i + 1) * 10) await saveNode(id, { ambition_order: (i + 1) * 10 });
      });
      await load();
    } catch (e) {
      const msg = (e as Error).message;
      await load();
      error = sqlHint(msg);
    }
  }

  // ---- + in the Ambitions view: something new, from Planning, or already on Pathways, for an ambition ----
  const LANE_KIND: Record<Lane, NodeKind> = {
    goals: "objective", awards: "award", publications: "project", teaching: "project", outreach: "project", grants: "grant",
  };
  let addFind = $state("");
  function openAdding(lane: Lane, amb: string) {
    addFind = "";
    panel = { adding: { lane, amb } };
  }
  /** Planning projects off Pathways whose name matches (with their open milestones off it), or all such projects. */
  const addFound = $derived.by(() => {
    const q = addFind.trim().toLocaleLowerCase();
    return liveProjects.map((p) => {
      const hit = !q || p.name.toLocaleLowerCase().includes(q);
      const ms = q ? p.milestone.filter((m) => m.status === "active" && !msOnMap.has(m.id) && (hit || m.title.toLocaleLowerCase().includes(q))) : [];
      return { p, ms, hit: hit && !onMap.has(p.id) };
    }).filter((x) => x.hit || x.ms.length);
  });
  /** What is on Pathways already in that lane, not serving the ambition yet. */
  const addExisting = $derived.by(() => {
    if (!panel || !("adding" in panel)) return [];
    const { lane, amb } = panel.adding;
    const q = addFind.trim().toLocaleLowerCase();
    return covItems.filter((n) => n.lane === lane && n.status === "active" && !servesOf(n.id).ids.includes(amb)
      && (!q || n.title.toLocaleLowerCase().includes(q)));
  });
  async function addFromPlanning(p: Project, m: Milestone | null, lane: Lane, amb: string) {
    panel = null;
    await placeProject(p, { lane }, m, amb);
  }
  async function addExistingTo(n: PwNode, amb: string) {
    panel = null;
    await tick(n.id, amb);
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
    const bits: string[] = [n.potential ? "potential project" : staged(n.kind) ? `${n.kind} · ${n.grant_stage ?? "drafting"}` : kindLabel(n.kind).toLowerCase()];
    if (n.milestone_id && n.project_id) bits[0] = `milestone of ${projById.get(n.project_id)?.name ?? "a project"}`;
    if (n.kind === "project" && n.hands_on) bits.unshift("hands-on");
    if (staged(n.kind) && n.end_on) bits.push(`deadline ${fmtMonth(n.end_on)}`);
    else if (n.start_on) bits.push(`${fmtMonth(n.start_on)} → ${n.end_on ? fmtMonth(n.end_on) : "…"}`);
    else if (n.end_on) bits.push(`by ${fmtMonth(n.end_on)}`);
    if (n.kind === "grant" && n.cost) bits.push(n.cost.toLocaleString());
    const fu = funding(n.id);
    if (fu) bits.push(fu);
    if (n.effort_pm) bits.push(`${n.effort_pm} pm`);
    if (n.fte) bits.push(`${Math.round(n.fte * 100)}%`);
    if (n.group_project_id) {
      const k = groupActivity.get(n.group_project_id) ?? 0;
      bits.push(`logbook ${k} this week`);
    }
    const who = (contributors.get(n.id) ?? []).map((u) => groupMembers.find((m) => m.user_id === u)?.display_name).filter(Boolean);
    if (who.length) bits.push(who.join(", "));
    const k = outputCount(n.id);
    if (k) bits.push(`${k} ${k === 1 ? "output" : "outputs"}`);
    const ex = expOf(n.id).length;
    if (ex) bits.push(`${ex} ${ex === 1 ? "experiment" : "experiments"}`);
    return bits.join(" · ");
  }
</script>

<section class="pathways" class:member>
  <span class="eyebrow">Pathways</span>
  <h1>Pathways</h1>

  <div class="views" role="tablist" aria-label="Pathways view">
    {#if !member}
      <button role="tab" aria-selected={view === "ambitions"} class:on={view === "ambitions"} onclick={() => setView("ambitions")}>Ambitions</button>
    {/if}
    <button role="tab" aria-selected={view === "map"} class:on={view === "map"} onclick={() => setView("map")}>Map</button>
    {#if !member}
      <button role="tab" aria-selected={view === "list"} class:on={view === "list"} onclick={() => setView("list")}>List</button>
    {/if}
    <button role="tab" aria-selected={view === "system"} class:on={view === "system"} onclick={() => setView("system")}>Outputs</button>
  </div>

  {#if view === "system"}
    <OutputsMap {outputs} links={outputLinks} titles={outputTitles} members={groupMembers} {me} supervisor={!member} readonly={!!preview.as}
                publications={publicationOptions} onchanged={load} />
  {:else if view === "ambitions" && !member}
    {#if error}<p class="error">{error}</p>{/if}
    {#if loading}<p class="muted">Loading…</p>{:else}
      <PwCoverage items={covItems} ambitions={covAmbitions} ticks={ambTicks} via={ambVia} ready={!!ambLinks} readonly={!!preview.as}
                  projectName={(id) => projById.get(id)?.name ?? "a project"}
                  onopen={(id) => { const n = nodes.find((x) => x.id === id); if (n) openEdit(n); }}
                  ontick={tick} onadd={openAdding} onnewamb={() => openNew("goal")} onreorder={reorderAmbitions} />
    {/if}
  {:else}
  <div class="toolbar">
    {#if !member}
      {#each NODE_KINDS.filter((k) => k.key !== "goal") as k (k.key)}
        <button class:primary={k.key === "project"} onclick={() => openNew(k.key)}>+ {k.label}</button>
      {/each}
      <button onclick={openImport} title="Put existing Planning projects on the map, linked to them">+ From Planning</button>
    {/if}
    <span class="spacer"></span>
    {#if view === "map"}
      <div class="years" role="group" aria-label="How far ahead">
        {#each [3, 5, 10, 15, 20] as y (y)}
          <button class:on={years === y} aria-pressed={years === y} onclick={() => setYears(y)}>{y} yr</button>
        {/each}
      </div>
    {/if}
    {#if view === "map" && !member}
      <button onclick={tidyRows} disabled={tidying} title="Close the empty lines in every row, keeping the order">{tidying ? "Tidying…" : "Tidy rows"}</button>
    {/if}
    <label class="toggle"><input type="checkbox" bind:checked={showAll} /> Show done and retired</label>
  </div>
  {#if view === "map" && shownAmbs.length}
    <div class="ambs" role="group" aria-label="Ambitions">
      <span class="muted">Ambitions</span>
      {#each shownAmbs as a (a.id)}
        <button class="amb-chip" class:on={focusOn === a.id} aria-pressed={focusOn === a.id} style:--amb={ambColour(a.id)}
                title={focusOn === a.id ? "Show them all again" : `Bring “${a.title}” forward`} onclick={() => setFocus(a.id)}>{a.title}</button>
      {/each}
      {#if drawn.some((n) => !servesOf(n.id).ids.length)}
        <button class="amb-chip" class:on={focusOn === "none"} aria-pressed={focusOn === "none"}
                title="What serves no ambition yet" onclick={() => setFocus("none")}>No ambition yet</button>
      {/if}
    </div>
  {/if}
  {#snippet projChip(p: Project)}
    <span class="tray-chip" role="button" tabindex="0" title={`Drag onto the map, into a lane — or press Enter to put it in its area's lane`}
          onpointerdown={(ev) => trayStart(ev, "project", p.id, p.name)}
          onkeydown={(ev) => { if (ev.key === "Enter") { ev.preventDefault(); placeProject(p); } }}>
      <span class="grip" aria-hidden="true">⠿</span>{p.name}
    </span>
  {/snippet}
  {#snippet msChip(p: Project, m: Milestone)}
    <span class="tray-chip ms" role="button" tabindex="0" title={`${m.title} — a milestone of ${p.name}. Drag onto the map, or press Enter`}
          onpointerdown={(ev) => trayStart(ev, "milestone", m.id, `◆ ${m.title}`)}
          onkeydown={(ev) => { if (ev.key === "Enter") { ev.preventDefault(); placeProject(p, undefined, m); } }}>
      <span class="grip" aria-hidden="true">⠿</span>◆ {m.title}
    </span>
  {/snippet}
  {#if view === "map" && !member && liveProjects.length}
    <details class="tray" bind:open={trayOpen}>
      <summary>
        Not on the map yet:
        {trayProjects.length} Planning {trayProjects.length === 1 ? "project" : "projects"} · find one for its milestones
      </summary>
      <input class="tray-find" type="search" bind:value={trayFind} placeholder="Find a project or milestone by name…"
             aria-label="Find a Planning project or milestone" />
      {#if trayFound}
        <div class="tray-found">
          {#each trayFound as x (x.p.id)}
            <div class="tray-proj">
              {#if onMap.has(x.p.id)}
                <span class="tray-on">{x.p.name} <span class="muted">· on the map</span></span>
              {:else}
                {@render projChip(x.p)}
              {/if}
              {#each x.ms as m (m.id)}{@render msChip(x.p, m)}{/each}
              {#if !x.ms.length}<span class="muted small">no open milestones off the map</span>{/if}
            </div>
          {:else}
            <p class="muted small">Nothing matches.</p>
          {/each}
        </div>
      {:else}
        <div class="tray-items">
          {#each trayProjects as p (p.id)}{@render projChip(p)}{/each}
          {#if !trayProjects.length}<span class="muted small">Every live project is on the map; find one for its milestones.</span>{/if}
        </div>
      {/if}
      <p class="hint muted">Drop a project or milestone in a lane, or focus it and press Enter for its area's lane{focusAmb() ? ` (it serves “${ambTitle(focusAmb()!)}”, brought forward)` : ""}.</p>
    </details>
  {/if}
  {#if trayDrag?.moved}
    <div class="tray-ghost" style:left={`${trayDrag.x + 12}px`} style:top={`${trayDrag.y + 8}px`}>{trayDrag.label}</div>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading}<p class="muted">Loading…</p>{/if}

  {#if view === "list" && !member}
    <PwList shown={visible} all={nodes.map(eff)} {links} {sub} onedit={openEdit} onadd={quickAdd} onchanged={load} />
  {:else}
  <div class="legend muted" aria-hidden="true">
    {#if member}
      <span class="hint">Your items, and the goals and objectives they lead to.</span>
    {:else}
      <span class="hint">Drag an item to move it in time or across lanes (hold Shift to keep its dates) · drag its right edge to stretch it · drag its ○ onto another item to link them · click to edit · its squares: the ambitions it serves (hollow: through its links)</span>
    {/if}
  </div>

  <div class="scroller" bind:clientWidth={width}>
    <div class="map" bind:this={mapEl} style:width={`${mapW}px`} style:height={`${mapH}px`} class:dragging={!!drag}>
      <!-- lanes -->
      {#each layout.bands as b, i (b.key)}
        <div class="lane lane-{b.lane}" class:alt={i % 2 === 1} style:top={`${b.top}px`}
             style:height={`${b.rows * ROW_H + 2 * PAD}px`}>
          <span class="lane-label">{LANES.find((l) => l.key === b.lane)?.label}</span>
        </div>
      {/each}
      <!-- axis -->
      {#each ticks as t (t.x)}
        <div class="tick" class:major={t.major} style:left={`${t.x}px`} style:height={`${mapH - 6}px`}><span>{t.label}</span></div>
      {/each}
      <div class="now" style:left={`${todayX}px`} style:height={`${mapH - 6}px`}><span>now</span></div>
      {#if hasCol}<div class="goals-head" style:left={`${x1 + GAP}px`} style:width={`${GOAL_W - GOAL_R}px`}>Goals · by {fmtDay(to).replace(/^1 /, "")}</div>{/if}

      <!-- links -->
      <svg class="links" width={mapW} height={mapH} aria-hidden="true">
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" class="ah" />
          </marker>
        </defs>
        {#each drawnLinks as dl (dl.l.id)}
          <path d={dl.d} class="lk-path" class:faded={fadedIds.has(dl.l.from_id) || fadedIds.has(dl.l.to_id)} marker-end="url(#arrow)">
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
        <div class="node kind-{n.kind} lane-{n.lane} {staged(n.kind) ? `gs-${n.grant_stage ?? "drafting"}` : ""}" class:potential={n.potential} class:hands-on={n.kind === "project" && n.hands_on} class:open-end={b.open}
             class:inactive={n.status !== "active"} class:moving={drag?.id === n.id}
             class:faded={fadedIds.has(n.id)}
             data-node={n.id} role="button" tabindex="0" title={`${n.title}${n.detail ? `\n${n.detail}` : ""}`}
             style:left={`${b.x}px`} style:top={`${b.y}px`} style:width={`${b.w}px`} style:height={`${NODE_H}px`}
             onpointerdown={(ev) => begin(ev, n, "move")}
             onkeydown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openEdit(n); } }}>
          <span class="n-title">{n.kind === "goal" ? "◎ " : n.kind === "gap" ? "? " : n.milestone_id ? "◆ " : ""}{#if n.kind === "project" && n.hands_on}<span class="hand" title="Hands-on">✋</span>{/if}{n.title}<FolderLink url={n.folder_url} /></span>
          <span class="n-sub">{n.status !== "active" ? `${n.status} · ` : ""}{sub(n)}</span>
          {#if !member}
            {@const sv = servesOf(n.id)}
            {#if sv.ids.length}
              <!-- the ambitions it serves (hollow: through its links) -->
              <span class="amb-marks" class:via={sv.via} aria-hidden="true">
                {#each sv.ids as a (a)}<i style:--amb={ambColour(a) ?? "var(--ink-soft)"} title={`${sv.via ? "Through its links: " : ""}${ambTitle(a)}`}></i>{/each}
              </span>
            {/if}
          {/if}
          {#if n.show_milestones && n.project_id}
            <!-- the Planning project's milestones, at their due dates (read from Planning, never copied) -->
            {#each projById.get(n.project_id)?.milestone ?? [] as m (m.id)}
              <!-- its due date (its own, or when the next milestone starts), else its start; never just the project's -->
              {@const d = milestoneDates(projById.get(n.project_id)!, m)}
              {@const dueKnown = d.dueFrom === "own" || d.dueFrom === "after"}
              {@const when = dueKnown ? d.due : d.startFrom === "own" || d.startFrom === "after" ? d.start : null}
              {#if when}
                <span class="ms-mark" class:ms-done={m.status === "done" || m.status === "dropped"}
                      style:left={`${Math.min(b.w - 6, Math.max(0, xOf(when) - b.x - 5))}px`}
                      title={`${m.title} · ${dueKnown ? "due" : "starts"} ${fmtMonth(when)}${m.status === "done" ? " · done" : ""}`}>◆</span>
              {/if}
            {/each}
          {/if}
          {#if !inColumn(n) && !member}
            <!-- pointer shortcuts; the editor's dates and Links do the same by keyboard -->
            <span class="resize" role="presentation" aria-hidden="true" title="Drag to change the end" onpointerdown={(ev) => begin(ev, n, "resize")}></span>
          {/if}
          {#if !member}<span class="connector" role="presentation" aria-hidden="true" title="Drag onto another item to link them" onpointerdown={(ev) => begin(ev, n, "link")}>○</span>{/if}
        </div>
      {/each}
    </div>
  </div>

  {#if !loading && !nodes.length}
    <p class="muted">Nothing on Pathways yet. Start in <em>Ambitions</em> with your two or three big ones, then add what serves them.</p>
  {/if}
  {/if}
  {/if}
</section>

<dialog bind:this={dialog} onclose={() => (panel = null)} class:sheet={!!panel && "node" in panel}>
  {#if panel && "adding" in panel}
    {@const ad = panel.adding}
    {@const laneLabel = LANES.find((l) => l.key === ad.lane)?.label ?? ""}
    <h2>{laneLabel} for “{ambTitle(ad.amb)}”</h2>
    <div class="add-new">
      <button class="primary" onclick={() => openNew(LANE_KIND[ad.lane], ad.lane, ad.amb)}>+ New {kindLabel(LANE_KIND[ad.lane]).toLowerCase()}…</button>
      {#if ad.lane === "publications"}
        <button onclick={() => openNew("person", ad.lane, ad.amb)}>+ New person…</button>
      {:else if ad.lane === "goals"}
        <button onclick={() => openNew("gap", ad.lane, ad.amb)}>+ New knowledge gap…</button>
      {/if}
    </div>
    <input class="imp-find" type="search" bind:value={addFind} placeholder="Find a Planning project, milestone or item by name…" aria-label="Find by name" />
    <div class="imp">
      {#if addExisting.length}
        <div class="imp-group">
          <p class="add-h">On Pathways already: tick it for this ambition</p>
          {#each addExisting.slice(0, 30) as n (n.id)}
            <button class="add-row" onclick={() => addExistingTo(n, ad.amb)}>{n.milestone_id ? "◆ " : ""}{n.title}
              <span class="muted">{n.start_on ? fmtMonth(n.start_on) : n.end_on ? `by ${fmtMonth(n.end_on)}` : "no dates"}</span></button>
          {/each}
        </div>
      {/if}
      <div class="imp-group">
        <p class="add-h">From Planning: put it on Pathways, in {laneLabel}{addFind.trim() ? "" : " (type a name to see milestones)"}</p>
        {#each addFound.slice(0, 60) as x (x.p.id)}
          {#if x.hit}
            <button class="add-row" onclick={() => addFromPlanning(x.p, null, ad.lane, ad.amb)}>{x.p.name}
              <span class="muted">{x.p.start_on || x.p.end_on ? `${x.p.start_on ? fmtMonth(x.p.start_on) : "…"} → ${x.p.end_on ? fmtMonth(x.p.end_on) : "…"}` : "no dates"}</span></button>
          {:else}
            <p class="add-parent muted">{x.p.name} <span>· on Pathways</span></p>
          {/if}
          {#each x.ms as m (m.id)}
            <button class="add-row add-ms" onclick={() => addFromPlanning(x.p, m, ad.lane, ad.amb)}>◆ {m.title}
              <span class="muted">milestone of {x.p.name}</span></button>
          {/each}
        {:else}
          <p class="muted small">{addFind.trim() ? "Nothing matches." : "Every live Planning project is on Pathways."}</p>
        {/each}
      </div>
    </div>
    <div class="imp-actions"><button onclick={() => (panel = null)}>Cancel</button></div>
  {:else if panel && "importing" in panel}
    <h2>Projects from Planning</h2>
    <p class="muted small">Tick the projects to put on the map. Each lands in its area's lane with its dates, linked to the Planning project.
      Find one by name to tick its milestones too, each on the map on its own.</p>
    <input class="imp-find" type="search" bind:value={importFind} placeholder="Find a project or milestone by name…" aria-label="Find a project or milestone" />
    <label class="small imp-ms"><input type="checkbox" bind:checked={importMilestones} /> Show the projects' milestones on their bars</label>
    {#if !importRows.length}
      <p class="muted">No live projects in Planning.</p>
    {:else if !importShown.length}
      <p class="muted">Nothing matches.</p>
    {/if}
    <div class="imp">
      {#each importGroups as g (g.group)}
        <details class="imp-group" open={!!importFind.trim() || g.rows.some((x) => !x.r.already)}>
          <summary><strong>{g.group}</strong> <span class="muted">{g.rows.length}</span></summary>
          {#each g.rows as { r, ms } (r.p.id)}
            <label class="imp-row" class:off={r.already}>
              <input type="checkbox" checked={r.pick} disabled={r.already} onchange={(e) => (r.pick = e.currentTarget.checked)} />
              <span class="imp-name">{r.p.name}</span>
              <span class="muted">
                {r.p.start_on || r.p.end_on ? `${r.p.start_on ? fmtMonth(r.p.start_on) : "…"} → ${r.p.end_on ? fmtMonth(r.p.end_on) : "…"}` : "no dates"}{r.p.milestone.length ? ` · ${r.p.milestone.length} milestones` : ""}
                · {LANES.find((l) => l.key === r.lane)?.label} lane{r.already ? " · already on the map" : ""}
              </span>
            </label>
            {#each ms as m (m.id)}
              {@const on = msOnMap.has(m.id)}
              {@const md = milestoneDates(r.p, m)}
              <label class="imp-row imp-msrow" class:off={on}>
                <input type="checkbox" bind:checked={importMs[m.id]} disabled={on} />
                <span>◆ {m.title}</span>
                <span class="muted">{md.start || md.due ? `${md.start ? fmtMonth(md.start) : "…"} → ${md.due ? fmtMonth(md.due) : "…"}` : "no dates"}{on ? " · already on the map" : ""}</span>
              </label>
            {/each}
          {/each}
        </details>
      {/each}
    </div>
    <div class="imp-actions">
      {#if importCount}
        <button class="primary" disabled={importing} onclick={addImported}>{importing ? "Adding…" : `Add ${importCount} to the map`}</button>
      {:else}
        <button class="primary" disabled>Tick projects or milestones to add</button>
      {/if}
      <button onclick={() => (panel = null)}>Cancel</button>
    </div>
  {:else if panel && "node" in panel}
    <div class="sheet-head">
      <h2>{cur ? cur.title : `New ${kindLabel(panel.draft?.kind ?? "project").toLowerCase()}`}</h2>
      {#if cur && isAmbition(cur) && !member}
        <span class="sheet-tag">Ambition</span>
      {/if}
      {#if cur && (cur.project_id || cur.group_project_id)}
        <!-- its project's actions (at the milestone, for a milestone's item) -->
        <a class="sheet-link" title="Its project's actions in the Logbook"
           href={cur.project_id ? `#/logbook?p=${cur.project_id}${cur.milestone_id ? `&m=${cur.milestone_id}` : ""}` : `#/logbook?g=${cur.group_project_id}`}>Logbook ›</a>
      {/if}
      <button type="button" class="x" aria-label="Close" onclick={() => (panel = null)}>✕</button>
    </div>
    {#if cur && (curProject || expLinks)}
      <div class="sheet-tabs" role="tablist" aria-label="What to change">
        <button role="tab" aria-selected={sheetTab === "item"} class:on={sheetTab === "item"} onclick={() => setSheetTab("item")}>On the map</button>
        {#if curProject}
          <button role="tab" aria-selected={sheetTab === "planning"} class:on={sheetTab === "planning"} onclick={() => setSheetTab("planning")}>In Planning</button>
        {/if}
        {#if expLinks}
          {@const k = expOf(cur.id).length}
          <button role="tab" aria-selected={sheetTab === "experiments"} class:on={sheetTab === "experiments"} onclick={() => setSheetTab("experiments")}>Experiments{k ? ` (${k})` : ""}</button>
        {/if}
      </div>
    {/if}
    {#if sheetTab === "planning" && curProject}
      <div class="sheet-body" data-unsaved-scope>
        <p class="muted small">Planning's own project, changed here: saving updates the map behind. (To delete the project itself, go to Planning; <em>Take off the map</em>, under <em>On the map</em>, leaves it there.)</p>
        {#key curProject.id}
          <ProjectEditor project={curProject} categories={editorCategories} categoryId={curProject.category_id} shared={sharedChoices}
                         onsaved={load} oncancel={() => (panel = null)} hideDelete />
        {/key}
        <Milestones project={curProject} {actualByMilestone} {privateShared} onchange={load} />
      </div>
    {:else if sheetTab === "experiments" && expLinks && cur}
      <div class="sheet-body">
        <PwExperiments nodeId={cur.id} topics={expTopics} notes={expNotes} linked={expOf(cur.id)} onchange={loadExp} />
      </div>
    {:else}
    {#key panel}
      <PwEditor node={panel.node} draft={panel.draft} {nodes} {links} {projects} {readings} {groupProjects} {tax} members={groupMembers}
        ambitions={allAmbs.map(eff).filter((a) => a.status === "active" || (panel && "node" in panel && !!panel.node
          && (a.id === panel.node.ambition_id || servesOf(panel.node.id).ids.includes(a.id)))).map((a) => ({ id: a.id, title: a.title }))}
        served={panel.node ? ambTicks.get(panel.node.id) ?? [] : panel.serves ?? []}
        via={panel.node && !ambTicks.get(panel.node.id)?.length ? (ambVia.get(panel.node.id) ?? []).map(ambTitle) : []}
        ambReady={!!ambLinks}
        contributors={panel.node ? contributors.get(panel.node.id) ?? [] : []} onsaved={saved} oncancel={() => (panel = null)} />
    {/key}
    {/if}
  {/if}
</dialog>

<style>
  .pathways {
    --lane-goals: var(--series-1);
    --lane-awards: #c0398a;
    --lane-publications: #6250d6;
    --lane-teaching: var(--series-2);
    --lane-outreach: var(--series-4);
    --lane-grants: var(--series-3);
    --lk: var(--ink-soft);
    /* the ambitions, apart from the lanes' colours */
    --amb-1: #0f766e; --amb-2: #b91c1c; --amb-3: #8a5a00; --amb-4: #475569;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme="light"])) .pathways {
      --lane-publications: #9085e9; --lane-awards: #e06aae;
      --amb-1: #2dd4bf; --amb-2: #f87171; --amb-3: #d9a441; --amb-4: #94a3b8;
    }
  }
  :global(:root[data-theme="dark"]) .pathways {
    --lane-publications: #9085e9; --lane-awards: #e06aae;
    --amb-1: #2dd4bf; --amb-2: #f87171; --amb-3: #d9a441; --amb-4: #94a3b8;
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
  .lane-goals .lane-label { color: var(--lane-goals); }
  .lane-awards .lane-label { color: var(--lane-awards); }
  .lane-teaching .lane-label { color: var(--lane-teaching); }
  .lane-outreach .lane-label { color: var(--lane-outreach); }
  .lane-publications .lane-label { color: var(--lane-publications); }
  .lane-grants .lane-label { color: var(--lane-grants); }
  .ambs { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; margin: 0 0 0.5rem; font-family: var(--font-ui); font-size: 0.82rem; }
  .amb-chip {
    font-size: 0.8rem; padding: 0.2rem 0.6rem; border-radius: 0; border-left: 4px solid var(--amb, var(--ink-soft));
    max-width: 18rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .amb-chip.on { background: color-mix(in srgb, var(--amb, var(--ink-soft)) 18%, var(--paper)); border-color: var(--amb, var(--ink-soft)); font-weight: 600; }
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
  .lk-path.faded { opacity: 0.15; }
  .ah { fill: var(--lk); }

  .node {
    position: absolute; box-sizing: border-box; display: grid; align-content: center; gap: 1px;
    padding: 0.2rem 1.1rem 0.2rem 0.55rem; background: var(--paper); border: 1px solid var(--rule);
    border-left: 4px solid var(--lane-goals); border-radius: 0; cursor: grab; overflow: visible;
    box-shadow: 0 1px 2px rgb(0 0 0 / 0.06);
  }
  .member .node { cursor: default; }
  .node:hover { box-shadow: 0 0 0 1px var(--ink-soft); z-index: 3; }
  .node:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .node.moving { opacity: 0.85; z-index: 5; box-shadow: 0 6px 16px rgb(0 0 0 / 0.2); }
  .node.lane-teaching { border-left-color: var(--lane-teaching); }
  .node.lane-outreach { border-left-color: var(--lane-outreach); }
  .node.lane-publications { border-left-color: var(--lane-publications); }
  .node.lane-awards { border-left-color: var(--lane-awards); }
  /* hands-on: your own research time goes into it */
  .node.hands-on { border-width: 2px; border-left-width: 7px; background: color-mix(in srgb, var(--accent) 9%, var(--paper)); }
  .node.hands-on .n-title { font-weight: 700; }
  .hand { margin-right: 0.25rem; }
  .node.lane-grants { border-left-color: var(--lane-grants); }
  .node.gs-drafting { border-style: dashed; border-left-style: solid; }
  .node.gs-awarded { border-width: 2px; border-left-width: 6px; background: color-mix(in srgb, var(--lane-grants) 10%, var(--paper)); }
  .node.gs-declined { opacity: 0.5; }
  .node.gs-declined .n-title { text-decoration: line-through; }
  .node.kind-goal { border-width: 2px; border-left-width: 6px; font-weight: 600; }
  /* the ambitions it serves: a square each, at the top right (hollow: through its links) */
  .amb-marks { position: absolute; top: -4px; right: 12px; display: flex; gap: 2px; pointer-events: auto; }
  .amb-marks i { width: 8px; height: 8px; background: var(--amb); box-shadow: 0 0 0 1.5px var(--paper); }
  .amb-marks.via i { background: var(--paper); box-shadow: inset 0 0 0 1.5px var(--amb), 0 0 0 1.5px var(--paper); }
  .node.kind-objective { background: color-mix(in srgb, var(--panel) 70%, var(--paper)); border-width: 2px; border-left-width: 6px; }
  .node.potential { border-style: dashed; border-left-style: dashed; background: transparent; }
  .node.kind-gap { border-style: dotted; border-left-style: solid; }
  .node.open-end { border-right-style: dashed; }
  .node.inactive { opacity: 0.5; }
  .node.faded { opacity: 0.18; }
  .node.faded:hover { opacity: 0.6; }
  .n-title { font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ms-mark { position: absolute; bottom: -8px; font-size: 0.8rem; line-height: 1; color: var(--accent); pointer-events: auto; text-shadow: 0 0 2px var(--paper), 0 0 2px var(--paper); cursor: help; }
  .ms-mark.ms-done { color: var(--ink-soft); opacity: 0.6; }
  .imp-ms { display: inline-flex; gap: 0.35rem; align-items: center; margin: 0.2rem 0; font-family: var(--font-ui); }
  .imp-ms input { width: auto; }
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
  /* an item opens at the side, the map still in sight behind */
  dialog.sheet {
    margin: 0 0 0 auto; width: min(44rem, 100vw); height: 100dvh; max-height: 100dvh; box-sizing: border-box;
    border-width: 0 0 0 1px; border-radius: 0; overflow-y: auto; box-shadow: -8px 0 24px rgb(0 0 0 / 0.15);
  }
  dialog.sheet::backdrop { background: rgb(0 0 0 / 0.12); }
  .sheet-head { display: flex; align-items: flex-start; gap: 0.6rem; }
  .sheet-head h2 { flex: 1; min-width: 0; overflow-wrap: anywhere; }
  .sheet-link { font-family: var(--font-ui); font-size: 0.82rem; white-space: nowrap; padding-top: 0.3rem; }
  .sheet-head .x { background: none; border: none; font-size: 1rem; padding: 0.1rem 0.4rem; color: var(--ink-soft); }
  .sheet-tabs { display: flex; gap: 0.25rem; margin: -0.3rem 0 0.9rem; font-family: var(--font-ui); border-bottom: 1px solid var(--rule); }
  .sheet-tabs button {
    font-size: 0.85rem; padding: 0.35rem 0.8rem; border: none; border-bottom: 2px solid transparent; border-radius: 0;
    background: none; color: var(--ink-soft); margin-bottom: -1px;
  }
  .sheet-tabs button.on { border-bottom-color: var(--ink); color: var(--ink); font-weight: 600; }
  .sheet-body .small { margin: 0 0 0.6rem; }

  /* ---- the tray: what is not on the map yet ---- */
  .tray { margin: 0 0 0.6rem; border: 1px dashed var(--rule); padding: 0.35rem 0.6rem; font-family: var(--font-ui); font-size: 0.82rem; }
  .tray summary { cursor: pointer; color: var(--ink-soft); }
  .tray-items { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.5rem 0 0.3rem; max-height: 9rem; overflow-y: auto; }
  .tray-chip {
    display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.2rem 0.55rem; border: 1px solid var(--rule);
    border-left: 3px solid var(--lane-publications); background: var(--paper); cursor: grab; user-select: none; touch-action: none;
    max-width: 22rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 0.8rem;
  }
  .tray-chip:hover { border-color: var(--ink-soft); }
  .tray-chip:focus-visible { outline: 2px solid var(--accent); }
  .tray-chip .grip { color: var(--ink-soft); }
  .tray .hint { margin: 0; font-size: 0.76rem; }
  .tray-chip.ms { border-left-color: var(--accent); }
  .tray-find { width: min(22rem, 100%); margin: 0.5rem 0 0; font-size: 0.82rem; padding: 0.25rem 0.5rem; }
  .tray-found { display: grid; gap: 0.4rem; margin: 0.5rem 0 0.3rem; max-height: 14rem; overflow-y: auto; }
  .tray-proj { display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .tray-on { font-size: 0.8rem; font-weight: 600; padding: 0.2rem 0.3rem; }
  .tray .small { font-size: 0.76rem; }
  .imp-find { width: 100%; margin: 0.3rem 0; }
  .imp-msrow { padding-left: 1.6rem; font-size: 0.82rem; }
  .tray-ghost {
    position: fixed; z-index: 80; pointer-events: none; padding: 0.25rem 0.6rem; background: var(--paper);
    border: 1px solid var(--ink-soft); box-shadow: 0 6px 16px rgb(0 0 0 / 0.2); font-family: var(--font-ui); font-size: 0.8rem;
    max-width: 20rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
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
  .add-new { display: flex; flex-wrap: wrap; gap: 0.4rem; font-family: var(--font-ui); margin-bottom: 0.4rem; }
  .add-h { margin: 0.1rem 0 0.3rem; font-size: 0.8rem; color: var(--ink-soft); }
  .add-row {
    display: flex; gap: 0.6rem; align-items: baseline; width: 100%; text-align: left; border: none; background: none;
    padding: 0.3rem 0.2rem; font-size: 0.85rem; border-radius: 0;
  }
  .add-row:hover { background: var(--panel); }
  .add-row .muted { font-size: 0.76rem; }
  .add-ms { padding-left: 1.4rem; }
  .add-parent { margin: 0.3rem 0 0; font-size: 0.82rem; font-weight: 600; }
  .add-parent span { font-weight: 400; }
  .sheet-tag { font-family: var(--font-ui); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-soft); padding-top: 0.45rem; }
  dialog h2 { margin: 0 0 0.8rem; font-size: 1.1rem; }
</style>
