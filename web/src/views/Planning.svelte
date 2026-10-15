<script lang="ts">
  import { supabase } from "../lib/supabase";

  type Category = { id: string; label: string; kind: string; sort_order: number };
  type Target = { effective_from: string; weekly_hours: number; email_weekly_hours: number };
  type Area = {
    id: string;
    label: string;
    sort_order: number;
    category: Category[];
    area_target: Target[];
  };

  let areas = $state<Area[]>([]);
  let weeksPerYear = $state(52);
  let error = $state("");
  let loading = $state(true);

  async function load() {
    const [a, s] = await Promise.all([
      supabase
        .from("area")
        .select("id,label,sort_order,category(id,label,kind,sort_order),area_target(effective_from,weekly_hours,email_weekly_hours)")
        .eq("is_active", true)
        .order("sort_order"),
      supabase.from("user_setting").select("weeks_per_year").maybeSingle(),
    ]);
    loading = false;
    if (a.error) return (error = a.error.message);
    areas = (a.data as Area[]).map((x) => ({
      ...x,
      category: [...x.category].sort((p, q) => p.sort_order - q.sort_order),
    }));
    if (s.data) weeksPerYear = Number(s.data.weeks_per_year);
  }
  load();

  // The target in force today: the latest effective_from not after today.
  function currentTarget(a: Area): Target | undefined {
    const today = new Date().toISOString().slice(0, 10);
    return a.area_target
      .filter((t) => t.effective_from <= today)
      .sort((p, q) => q.effective_from.localeCompare(p.effective_from))[0];
  }

  const totals = $derived.by(() => {
    let weekly = 0, email = 0;
    for (const a of areas) {
      const t = currentTarget(a);
      if (t) { weekly += Number(t.weekly_hours); email += Number(t.email_weekly_hours); }
    }
    return { weekly, email, annual: (weekly + email) * weeksPerYear };
  });
</script>

<section>
  <span class="eyebrow">Planning</span>
  <h1>Allocation</h1>
  <p class="muted">Weekly targets per area and the categories under each. Projects and the 12-month horizon come next.</p>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if !areas.length}
    <p class="muted">No areas yet — has 0002_seed_taxonomy.sql been run?</p>
  {:else}
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Area</th><th class="num">Time h/wk</th><th class="num">Email h/wk</th><th>Categories</th></tr>
        </thead>
        <tbody>
          {#each areas as a (a.id)}
            {@const t = currentTarget(a)}
            <tr>
              <td><strong>{a.label}</strong></td>
              <td class="num">{t ? Number(t.weekly_hours) : "—"}</td>
              <td class="num">{t ? Number(t.email_weekly_hours) : "—"}</td>
              <td>
                {#each a.category as c (c.id)}
                  <span class="chip" title={c.kind}>{c.label}<small>{c.kind}</small></span>
                {/each}
              </td>
            </tr>
          {/each}
        </tbody>
        <tfoot>
          <tr>
            <td>Total</td>
            <td class="num">{totals.weekly}</td>
            <td class="num">{totals.email}</td>
            <td>{totals.weekly + totals.email} h/wk × {weeksPerYear} weeks = <strong>{totals.annual} h/year</strong></td>
          </tr>
        </tfoot>
      </table>
    </div>
  {/if}
</section>

<style>
  .table-wrap { overflow-x: auto; margin-top: 1rem; }
  table { border-collapse: collapse; width: 100%; font-family: var(--font-ui); font-size: 0.92rem; }
  th, td { text-align: left; padding: 0.55rem 0.6rem; border-bottom: 1px solid var(--rule); vertical-align: top; }
  th { color: var(--ink-soft); font-weight: 500; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  tfoot td { border-bottom: none; font-weight: 500; }
  .chip {
    display: inline-flex; gap: 0.35rem; align-items: baseline;
    background: var(--panel); border-radius: 999px;
    padding: 0.1rem 0.6rem; margin: 0 0.3rem 0.3rem 0;
  }
  .chip small { color: var(--ink-soft); font-size: 0.72rem; }
</style>
