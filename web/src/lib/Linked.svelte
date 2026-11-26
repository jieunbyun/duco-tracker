<script lang="ts">
  // Text with each web address in it shown as a short "link" (the address shows on hover).
  import { linkParts, linkLabel } from "./links";
  let { text }: { text: string } = $props();
</script>

{#each linkParts(text) as part, i (i)}{#if part.url}<a class="ulink" href={part.url} target="_blank" rel="noopener" title={part.url}>{linkLabel(part.url)}</a>{:else}{part.text}{/if}{/each}

<style>
  .ulink { text-decoration: underline; color: var(--accent); }
</style>
