<script lang="ts">
  import { assetGraph, catalogueYaml } from "./assets";
  import type { Asset } from "./assets";
  import type { PwNode } from "./pathways";

  type Props = { assets: Asset[]; nodes: PwNode[]; onadd: () => void; onedit: (a: Asset) => void };
  let { assets, nodes, onadd, onedit }: Props = $props();

  let showRetired = $state(false);
  const graph = $derived(assetGraph(assets));
  const nameOf = (id: string | null) => (id ? nodes.find((n) => n.id === id)?.title ?? null : null);

  // ---- layout: one column per level, ordered to keep arrows short ------------------
  const COL_W = 250, CARD_W = 200, CARD_H = 58, ROW_H = 78, TOP = 30, LEFT = 16;
  type Item = { id: string; x: number; y: number; source?: string; asset?: Asset };
  const layout = $derived.by(() => {
    const live = assets.filter((a) => a.status !== "retired");
    const cols = new Map<number, string[]>();
    for (const s of graph.sources) cols.set(0, [...(cols.get(0) ?? []), s.id]);
    for (const a of live) {
      const l = graph.level.get(a.id) ?? 1;
      cols.set(l, [...(cols.get(l) ?? []), a.id]);
    }
    // order each column by where its predecessors sit (a single barycentre pass)
    const row = new Map<string, number>();
    const preds = new Map<string, string[]>();
    for (const e of graph.edges) preds.set(e.to, [...(preds.get(e.to) ?? []), e.from]);
    for (const s of graph.sources) for (const c of s.consumers) preds.set(c, [...(preds.get(c) ?? []), s.id]);
    const label = (id: string) => graph.sources.find((s) => s.id === id)?.type ?? live.find((a) => a.id === id)?.name ?? "";
    const levels = [...cols.keys()].sort((a, b) => a - b);
    for (const l of levels) {
      const ids = cols.get(l)!;
      const score = (id: string) => {
        const ps = (preds.get(id) ?? []).filter((p) => row.has(p));
        return ps.length ? ps.reduce((s, p) => s + row.get(p)!, 0) / ps.length : Number.MAX_SAFE_INTEGER;
      };
      ids.sort((a, b) => score(a) - score(b) || label(a).localeCompare(label(b)));
      ids.forEach((id, i) => row.set(id, i));
    }
    const items: Item[] = [];
    for (const l of levels) {
      for (const id of cols.get(l)!) {
        const s = graph.sources.find((x) => x.id === id);
        items.push({ id, x: LEFT + l * COL_W, y: TOP + row.get(id)! * ROW_H, source: s?.type, asset: live.find((a) => a.id === id) });
      }
    }
    const width = LEFT + (Math.max(0, ...levels) + 1) * COL_W;
    const height = TOP + Math.max(1, ...[...cols.values()].map((c) => c.length)) * ROW_H + 10;
    return { items, width, height };
  });
  const pos = $derived(new Map(layout.items.map((i) => [i.id, i])));

  const arrows = $derived([
    ...graph.edges.map((e) => ({ from: e.from, to: e.to, label: e.types.join(", "), source: false })),
    ...graph.sources.flatMap((s) => s.consumers.map((c) => ({ from: s.id, to: c, label: "", source: true }))),
  ].map((a) => {
    const p = pos.get(a.from), q = pos.get(a.to);
    if (!p || !q) return null;
    const sx = p.x + (p.source ? 150 : CARD_W), sy = p.y + CARD_H / 2;
    const tx = q.x, ty = q.y + CARD_H / 2;
    const dx = Math.max(30, (tx - sx) / 2);
    return { ...a, d: `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`, lx: (sx + tx) / 2, ly: (sy + ty) / 2 - 4 };
  }).filter((a) => !!a));

  const retired = $derived(assets.filter((a) => a.status === "retired"));

  let copied = $state(false);
  async function copyCatalogue() {
    try {
      await navigator.clipboard.writeText(catalogueYaml(assets.filter((a) => a.status !== "retired"), nameOf));
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch { copied = false; }
  }
</script>

<div class="is">
  <div class="is-bar">
    <button class="primary" onclick={onadd}>+ Asset</button>
    <button onclick={copyCatalogue} disabled={!assets.length} title="Asset cards as YAML — the start of a shared group catalogue">
      {copied ? "Copied" : "Copy catalogue (YAML)"}
    </button>
    <span class="muted note">
      {assets.length - retired.length} assets ·
      {graph.sources.length} open {graph.sources.length === 1 ? "input" : "inputs"} nothing produces yet
    </span>
  </div>

  {#if !layout.items.length}
    <p class="muted empty">No assets yet. Add one — an algorithm, a model, a dataset — with what it takes in and gives out; assets join up wherever an output matches an input.</p>
  {:else}
    <div class="is-scroll">
      <div class="is-map" style:width={`${layout.width}px`} style:height={`${layout.height}px`}>
        <div class="col-head" style:left={`${LEFT}px`}>Open inputs</div>
        <svg class="arrows" width={layout.width} height={layout.height} aria-hidden="true">
          <defs>
            <marker id="is-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="ah" /></marker>
          </defs>
          {#each arrows as a, i (i)}
            <path d={a!.d} class:source={a!.source} marker-end="url(#is-arrow)" />
            {#if a!.label}<text x={a!.lx} y={a!.ly} text-anchor="middle">{a!.label}</text>{/if}
          {/each}
        </svg>
        {#each layout.items as it (it.id)}
          {#if it.source}
            <div class="src" style:left={`${it.x}px`} style:top={`${it.y + 14}px`} title="Nothing in the system produces this yet">{it.source}</div>
          {:else if it.asset}
            {@const a = it.asset}
            {@const spare = graph.unused.get(a.id) ?? []}
            <button class="card st-{a.status}" style:left={`${it.x}px`} style:top={`${it.y}px`} style:width={`${CARD_W}px`} style:height={`${CARD_H}px`}
                    onclick={() => onedit(a)}
                    title={`${a.name}${a.purpose ? `\n${a.purpose}` : ""}\nin: ${a.inputs.join(", ") || "—"}\nout: ${a.outputs.join(", ") || "—"}`}>
              <span class="c-name">{a.name}</span>
              <span class="c-sub">{a.kind} · {a.status}{nameOf(a.owner_node_id) ? ` · ${nameOf(a.owner_node_id)}` : ""}</span>
              {#if spare.length}<span class="c-spare">→ {spare.join(", ")}</span>{/if}
            </button>
          {/if}
        {/each}
      </div>
    </div>
    <p class="muted legend">
      Dashed grey: inputs nothing produces yet — the gaps. A card's “→” line lists outputs nothing takes in yet.
      Idea dashed · prototype plain · validated bold.
    </p>
  {/if}

  {#if retired.length}
    <details class="retired">
      <summary class="muted">Retired ({retired.length})</summary>
      {#each retired as a (a.id)}<button class="link" onclick={() => onedit(a)}>{a.name}</button>{/each}
    </details>
  {/if}
</div>

<style>
  .is { font-family: var(--font-ui); }
  .is-bar { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin: 0.6rem 0; }
  .is-bar button { font-size: 0.85rem; padding: 0.35rem 0.7rem; }
  .note { font-size: 0.8rem; }
  .empty { max-width: 40rem; }
  .is-scroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); }
  .is-map { position: relative; }
  .col-head { position: absolute; top: 6px; font-size: 0.72rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.06em; }
  .arrows { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
  .arrows path { fill: none; stroke: var(--accent); stroke-width: 1.5; }
  .arrows path.source { stroke: var(--ink-soft); stroke-dasharray: 4 4; }
  .arrows .ah { fill: var(--accent); }
  .arrows text { font-size: 10px; fill: var(--ink-soft); paint-order: stroke; stroke: var(--paper); stroke-width: 3px; }
  .src {
    /* a fixed width, so its arrow starts right at its edge */
    position: absolute; box-sizing: border-box; width: 150px; padding: 0.2rem 0.55rem; font-size: 0.75rem; color: var(--ink-soft);
    border: 1px dashed var(--ink-soft); border-radius: 999px; background: var(--paper);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .card {
    position: absolute; display: grid; align-content: center; gap: 1px; text-align: left; padding: 0.3rem 0.6rem;
    background: var(--paper); border: 1px solid var(--rule); border-left: 4px solid var(--accent); border-radius: 6px;
  }
  .card:hover { box-shadow: 0 0 0 1px var(--ink-soft); }
  .card.st-idea { border-style: dashed; border-left-style: dashed; }
  .card.st-validated { border-width: 2px; border-left-width: 5px; }
  .c-name { font-size: 0.82rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .c-sub, .c-spare { font-size: 0.68rem; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .c-spare { color: var(--accent); }
  .legend { font-size: 0.78rem; margin: 0.4rem 0 0; }
  .retired { margin-top: 0.8rem; font-size: 0.85rem; }
  .retired summary { cursor: pointer; }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0.1rem 0.4rem; }
</style>
