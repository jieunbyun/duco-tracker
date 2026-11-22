<script lang="ts">
  // The way back to the tab you came from, kept in sight while you scroll.
  let { href, text }: { href: string; text: string } = $props();
</script>

<a class="back" {href}>← {text}</a>

<style>
  .back {
    position: fixed; left: 1rem; bottom: 1.2rem; z-index: 59;
    padding: 0.45rem 0.9rem; background: var(--paper); color: var(--ink); border: 1px solid var(--rule);
    border-radius: var(--radius); box-shadow: 0 4px 14px rgb(0 0 0 / 0.15);
    font-family: var(--font-ui); font-size: 0.85rem; text-decoration: none;
  }
  .back:hover { border-color: var(--ink-soft); }
</style>
