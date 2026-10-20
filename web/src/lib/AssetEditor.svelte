<script lang="ts">
  import { untrack } from "svelte";
  import { ASSET_KINDS, ASSET_STATUSES, saveAsset, deleteAsset, parseList } from "./assets";
  import type { Asset, AssetFields } from "./assets";
  import type { PwNode } from "./pathways";

  type Props = {
    asset: Asset | null; // null = new
    nodes: PwNode[]; // people and projects to attach it to
    known: string[]; // input/output names already in use, offered as suggestions
    onsaved: () => void;
    oncancel: () => void;
  };
  let { asset, nodes, known, onsaved, oncancel }: Props = $props();

  const a0 = untrack(() => asset);
  let f = $state({
    name: a0?.name ?? "",
    kind: a0?.kind ?? "algorithm",
    status: a0?.status ?? "idea",
    purpose: a0?.purpose ?? "",
    inputs: (a0?.inputs ?? []).join(", "),
    outputs: (a0?.outputs ?? []).join(", "),
    owner_node_id: a0?.owner_node_id ?? "",
    project_node_id: a0?.project_node_id ?? "",
    location: a0?.location ?? "",
  });
  let busy = $state(false);
  let error = $state("");

  const people = $derived(nodes.filter((n) => n.kind === "person").sort((a, b) => a.title.localeCompare(b.title)));
  const projectNodes = $derived(nodes.filter((n) => n.kind === "project").sort((a, b) => a.title.localeCompare(b.title)));

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!f.name.trim()) return (error = "Give the asset a name.");
    busy = true;
    error = "";
    try {
      const fields: Partial<AssetFields> = {
        name: f.name.trim(), kind: f.kind as Asset["kind"], status: f.status as Asset["status"],
        purpose: f.purpose.trim() || null, inputs: parseList(f.inputs), outputs: parseList(f.outputs),
        owner_node_id: f.owner_node_id || null, project_node_id: f.project_node_id || null,
        location: f.location.trim() || null,
      };
      await saveAsset(a0?.id ?? null, fields);
      onsaved();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
  async function remove() {
    if (!a0 || !confirm(`Delete the asset “${a0.name}”?`)) return;
    busy = true;
    try {
      await deleteAsset(a0.id);
      onsaved();
    } catch (e) {
      error = (e as Error).message;
      busy = false;
    }
  }
</script>

<form class="as-form" onsubmit={save}>
  <label class="span2">Name <input bind:value={f.name} required placeholder="e.g. Exact inference for Bayesian networks" /></label>
  <label>Kind <select bind:value={f.kind}>{#each ASSET_KINDS as k (k)}<option value={k}>{k}</option>{/each}</select></label>
  <label class="wide">Purpose <textarea rows="2" bind:value={f.purpose} placeholder="What it does, in a sentence"></textarea></label>
  <label class="wide">Takes in (inputs, separated by commas)
    <input bind:value={f.inputs} list="io-names" placeholder="e.g. BN model, evidence" />
  </label>
  <label class="wide">Gives out (outputs, separated by commas)
    <input bind:value={f.outputs} list="io-names" placeholder="e.g. posterior marginals" />
  </label>
  <p class="hint wide">Assets connect wherever one's output has the same name as another's input — reuse the names suggested as you type.</p>
  <datalist id="io-names">{#each known as k (k)}<option value={k}></option>{/each}</datalist>

  <label>Status <select bind:value={f.status}>{#each ASSET_STATUSES as s (s)}<option value={s}>{s}</option>{/each}</select></label>
  <label>Owner
    <select bind:value={f.owner_node_id}>
      <option value="">— none —</option>
      {#each people as n (n.id)}<option value={n.id}>{n.title}</option>{/each}
    </select>
  </label>
  <label>Produced by (project)
    <select bind:value={f.project_node_id}>
      <option value="">— none —</option>
      {#each projectNodes as n (n.id)}<option value={n.id}>{n.title}</option>{/each}
    </select>
  </label>
  <label class="wide">Where it lives (repository, DOI…) <input bind:value={f.location} placeholder="https://github.com/…" /></label>

  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{a0 ? "Save" : "Add asset"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if a0}<button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>{/if}
  </div>
</form>

<style>
  .as-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.65rem 1rem; font-family: var(--font-ui); }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .span2 { grid-column: span 2; }
  .hint { font-size: 0.78rem; color: var(--ink-soft); margin: -0.3rem 0 0; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
  @media (max-width: 40rem) { .as-form { grid-template-columns: 1fr; } .span2 { grid-column: auto; } }
</style>
