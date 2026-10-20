// The group's outputs: what has been developed, by whom, when, for which
// publications, and where its data or code lives (0011_assets.sql,
// 0018_outputs.sql). Three categories, joined by drawn links. Every member
// sees them all; an output is changed by whoever added it, its contributors,
// and the supervisor.
import { supabase } from "./supabase";
import { check } from "./data";

export const CATEGORIES = [
  { key: "inference", label: "Inference algorithms" },
  { key: "data_model", label: "Data, models & simulators" },
  { key: "other", label: "Others" },
] as const;
export type Category = (typeof CATEGORIES)[number]["key"];
export const OUTPUT_STATUSES = ["idea", "prototype", "validated", "retired"] as const;

export type Output = {
  id: string;
  user_id: string; // who added it
  name: string;
  category: Category;
  status: (typeof OUTPUT_STATUSES)[number];
  purpose: string | null;
  developed_on: string | null;
  location: string | null; // where the data or code lives
  contributors: string[]; // member ids
  publications: string[]; // Pathways items in Publications & code/database
};
export type OutputFields = Pick<Output, "name" | "category" | "status" | "purpose" | "developed_on" | "location">;
export type OutputLink = { id: string; from_id: string; to_id: string };

type Row = Omit<Output, "contributors" | "publications"> & {
  asset_contributor: { user_id: string }[]; asset_publication: { node_id: string }[];
};
/** Everything on the map, and the titles of the publications it refers to. Empty before 0018 is run. */
export async function loadOutputs(): Promise<{ outputs: Output[]; links: OutputLink[]; titles: Map<string, string> }> {
  const [o, l, t] = await Promise.all([
    supabase.from("pw_asset")
      .select("id,user_id,name,category,status,purpose,developed_on,location,asset_contributor(user_id),asset_publication(node_id)")
      .order("developed_on", { nullsFirst: false }).order("created_at"),
    supabase.from("asset_link").select("id,from_id,to_id"),
    supabase.rpc("output_publications"),
  ]);
  if (o.error || l.error) return { outputs: [], links: [], titles: new Map() };
  return {
    outputs: ((o.data ?? []) as Row[]).map(({ asset_contributor, asset_publication, ...x }) => ({
      ...x, contributors: asset_contributor.map((c) => c.user_id), publications: asset_publication.map((p) => p.node_id),
    })),
    links: (l.data ?? []) as OutputLink[],
    titles: new Map(((t.data ?? []) as { node_id: string; title: string }[]).map((r) => [r.node_id, r.title])),
  };
}

/** Save an output, its contributors and its publications; returns its id. */
export async function saveOutput(id: string | null, fields: OutputFields, contributors: string[], publications: string[],
                                 was: Output | null): Promise<string> {
  let outId = id;
  if (id) await check(supabase.from("pw_asset").update(fields).eq("id", id));
  else outId = (await check<{ id: string }>(supabase.from("pw_asset").insert(fields).select("id").single()))!.id;
  const sync = async (table: string, col: string, want: string[], had: string[]) => {
    const add = want.filter((x) => !had.includes(x));
    const drop = had.filter((x) => !want.includes(x));
    if (add.length) await check(supabase.from(table).insert(add.map((v) => ({ asset_id: outId, [col]: v }))));
    if (drop.length) await check(supabase.from(table).delete().eq("asset_id", outId!).in(col, drop));
  };
  await sync("asset_contributor", "user_id", contributors, was?.contributors ?? []);
  await sync("asset_publication", "node_id", publications, was?.publications ?? []);
  return outId!;
}
export async function deleteOutput(id: string): Promise<void> {
  await check(supabase.from("pw_asset").delete().eq("id", id));
}
export async function linkOutputs(from_id: string, to_id: string): Promise<void> {
  await check(supabase.from("asset_link").upsert({ from_id, to_id }, { onConflict: "from_id,to_id", ignoreDuplicates: true }));
}
export async function unlinkOutputs(id: string): Promise<void> {
  await check(supabase.from("asset_link").delete().eq("id", id));
}

// ---- the catalogue, as plain cards ---------------------------------------------
const y = (v: string) => (/^[\w .()/-]+$/.test(v) && !/^\s|\s$/.test(v) ? v : JSON.stringify(v));
const list = (xs: string[]) => `[${xs.map(y).join(", ")}]`;

/** YAML cards — the shape a shared repository's catalogue could take. */
export function catalogueYaml(outputs: Output[], links: OutputLink[], nameOf: (uid: string) => string,
                              titleOf: (nodeId: string) => string): string {
  const byId = new Map(outputs.map((o) => [o.id, o]));
  return outputs.map((o) => [
    `- name: ${y(o.name)}`,
    `  category: ${o.category}`,
    `  status: ${o.status}`,
    o.developed_on ? `  developed: ${o.developed_on.slice(0, 7)}` : null,
    o.purpose ? `  purpose: ${y(o.purpose)}` : null,
    o.contributors.length ? `  contributors: ${list(o.contributors.map(nameOf))}` : null,
    o.publications.length ? `  publications: ${list(o.publications.map(titleOf))}` : null,
    o.location ? `  url: ${y(o.location)}` : null,
    (() => {
      const to = links.filter((l) => l.from_id === o.id).map((l) => byId.get(l.to_id)?.name).filter((n): n is string => !!n);
      return to.length ? `  feeds: ${list(to)}` : null;
    })(),
  ].filter(Boolean).join("\n")).join("\n");
}
