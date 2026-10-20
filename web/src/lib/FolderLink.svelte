<script lang="ts">
  // A small 📁 that opens an item's folder on OneDrive, without opening the item.
  let { url, label = "" }: { url: string | null | undefined; label?: string } = $props();
</script>

{#if url}
  <a class="folder" href={url} target="_blank" rel="noopener noreferrer" title="Open its folder on OneDrive"
     onclick={(ev) => ev.stopPropagation()} onpointerdown={(ev) => ev.stopPropagation()}>📁{label ? ` ${label}` : ""}</a>
{/if}

<style>
  .folder { text-decoration: none; font-size: 0.85em; margin: 0 0.2rem; white-space: nowrap; }
  .folder:hover { text-decoration: underline; }
</style>
