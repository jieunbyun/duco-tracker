<script lang="ts">
  // Everything in the app as one JSON file, to keep on OneDrive (Me › Backups).
  import { exportEverything, rowCount } from "./backup";
  import { download } from "./group";

  let exporting = $state<string | null>(null);
  let exported = $state("");
  async function exportAll() {
    exporting = "Reading…";
    exported = "";
    try {
      const b = await exportEverything((done, total) => (exporting = `Reading ${done} of ${total} tables…`));
      download(`duco-backup-${b.exported_at.slice(0, 10)}.json`, JSON.stringify(b, null, 1));
      exported = `Saved ${rowCount(b).toLocaleString()} records from ${Object.keys(b.tables).length} tables` +
        (b.missing.length ? ` (not yet set up: ${b.missing.join(", ")})` : "") + ". Put the file in OneDrive › Me › Backups.";
    } catch (e) {
      exported = `Could not export: ${(e as Error).message}`;
    } finally {
      exporting = null;
    }
  }
</script>

<div class="data">
  <h2>Your data</h2>
  <p class="muted">
    Files live on OneDrive; the app keeps the links. For a copy of everything in the app itself, export it now and
    then (monthly, say) and keep the file in OneDrive › Me › Backups.
  </p>
  <button onclick={exportAll} disabled={!!exporting}>{exporting ?? "Export everything (JSON)"}</button>
  {#if exported}<p class="muted small">{exported}</p>{/if}
</div>

<style>
  .data { margin-top: 2rem; font-family: var(--font-ui); }
  .data p { font-size: 0.88rem; max-width: 46rem; }
  .small { font-size: 0.85rem; }
</style>
