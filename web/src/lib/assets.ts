// The information system: asset cards connected by what they take in and give
// out. An arrow runs from A to B wherever one of A's outputs is one of B's
// inputs; inputs nobody produces are the system's open ends ("sources").
import { supabase } from "./supabase";
import { check } from "./data";

export const ASSET_KINDS = ["algorithm", "model", "dataset", "software", "knowledge", "other"] as const;
export const ASSET_STATUSES = ["idea", "prototype", "validated", "retired"] as const;

export type Asset = {
  id: string;
  name: string;
  kind: (typeof ASSET_KINDS)[number];
  status: (typeof ASSET_STATUSES)[number];
  purpose: string | null;
  inputs: string[];
  outputs: string[];
  owner_node_id: string | null;
  project_node_id: string | null;
  location: string | null;
};
export type AssetFields = Omit<Asset, "id">;

export async function loadAssets(): Promise<Asset[]> {
  return (await check<Asset[]>(
    supabase.from("pw_asset").select("id,name,kind,status,purpose,inputs,outputs,owner_node_id,project_node_id,location").order("created_at"),
  )) ?? [];
}
export async function saveAsset(id: string | null, fields: Partial<AssetFields>): Promise<void> {
  await check(id ? supabase.from("pw_asset").update(fields).eq("id", id) : supabase.from("pw_asset").insert(fields));
}
export async function deleteAsset(id: string): Promise<void> {
  await check(supabase.from("pw_asset").delete().eq("id", id));
}

/** "a, b; c" or one per line → ["a", "b", "c"], trimmed, without repeats. */
export function parseList(text: string): string[] {
  const seen = new Set<string>();
  return text.split(/[,;\n]/).map((s) => s.trim()).filter((s) => s && !seen.has(s.toLowerCase()) && seen.add(s.toLowerCase()));
}
const key = (t: string) => t.trim().toLowerCase();

// ---- the graph -----------------------------------------------------------------
export type Edge = { from: string; to: string; types: string[] };
export type Source = { id: string; type: string; consumers: string[] };
export type Graph = {
  edges: Edge[]; // asset → asset
  sources: Source[]; // inputs nobody produces → their consumers
  level: Map<string, number>; // column: sources 0, assets from 1
  unused: Map<string, string[]>; // an asset's outputs nobody takes in
};

export function assetGraph(assets: Asset[]): Graph {
  const live = assets.filter((a) => a.status !== "retired");
  const producers = new Map<string, string[]>();
  for (const a of live) for (const o of a.outputs) producers.set(key(o), [...(producers.get(key(o)) ?? []), a.id]);

  const pairs = new Map<string, Edge>();
  const sources = new Map<string, Source>();
  for (const b of live) {
    for (const i of b.inputs) {
      const ps = (producers.get(key(i)) ?? []).filter((p) => p !== b.id);
      if (!ps.length) {
        const s = sources.get(key(i)) ?? { id: `src:${key(i)}`, type: i.trim(), consumers: [] };
        if (!s.consumers.includes(b.id)) s.consumers.push(b.id);
        sources.set(key(i), s);
      }
      for (const a of ps) {
        const e = pairs.get(`${a}>${b.id}`) ?? { from: a, to: b.id, types: [] };
        if (!e.types.some((t) => key(t) === key(i))) e.types.push(i.trim());
        pairs.set(`${a}>${b.id}`, e);
      }
    }
  }
  const edges = [...pairs.values()];

  // columns by longest path from the sources; a loop stops growing at n
  const level = new Map<string, number>(live.map((a) => [a.id, 1]));
  for (let pass = 0; pass < live.length; pass++) {
    let changed = false;
    for (const e of edges) {
      const want = Math.min(live.length, (level.get(e.from) ?? 1) + 1);
      if (want > (level.get(e.to) ?? 1)) { level.set(e.to, want); changed = true; }
    }
    if (!changed) break;
  }
  for (const s of sources.values()) level.set(s.id, 0);

  const consumed = new Set(live.flatMap((a) => a.inputs.map(key)));
  const unused = new Map(live.map((a) => [a.id, a.outputs.filter((o) => !consumed.has(key(o)))]));
  return { edges, sources: [...sources.values()], level, unused };
}

// ---- the catalogue, as plain asset cards ---------------------------------------
const y = (v: string) => (/^[\w .()/-]+$/.test(v) && !/^\s|\s$/.test(v) ? v : JSON.stringify(v));
const list = (xs: string[]) => `[${xs.map(y).join(", ")}]`;

/** YAML asset cards — the shape a shared repository's catalogue could take. */
export function catalogueYaml(assets: Asset[], nameOf: (id: string | null) => string | null): string {
  return assets.map((a) => [
    `- name: ${y(a.name)}`,
    `  kind: ${a.kind}`,
    `  status: ${a.status}`,
    a.purpose ? `  purpose: ${y(a.purpose)}` : null,
    `  inputs: ${list(a.inputs)}`,
    `  outputs: ${list(a.outputs)}`,
    nameOf(a.owner_node_id) ? `  owner: ${y(nameOf(a.owner_node_id)!)}` : null,
    nameOf(a.project_node_id) ? `  project: ${y(nameOf(a.project_node_id)!)}` : null,
    a.location ? `  location: ${y(a.location)}` : null,
  ].filter(Boolean).join("\n")).join("\n");
}
