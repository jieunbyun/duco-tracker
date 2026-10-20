<script lang="ts" generics="T extends { id: string }">
  // A list you can put in your own order: drag a row's ⠿ handle (mouse or
  // touch), or focus the handle and use the arrow keys. The window follows the
  // pointer for the whole drag, as rows move under it.
  import type { Snippet } from "svelte";

  type Props = {
    items: T[];
    row: Snippet<[T]>;
    onreorder: (ids: string[]) => void | Promise<void>;
    disabled?: boolean;
  };
  let { items, row, onreorder, disabled = false }: Props = $props();

  const group = crypto.randomUUID().slice(0, 8); // keeps nested lists apart
  let order = $state<string[] | null>(null); // ids, while dragging
  let dragging = $state<string | null>(null);
  const shown = $derived(order ? order.map((id) => items.find((x) => x.id === id)).filter((x): x is T => !!x) : items);

  function start(ev: PointerEvent, id: string) {
    if (ev.button !== 0 || disabled) return;
    ev.preventDefault();
    dragging = id;
    order = items.map((x) => x.id);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }
  function move(ev: PointerEvent) {
    if (!dragging || !order) return;
    const over = (document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null)
      ?.closest<HTMLElement>(`li[data-sort="${group}"]`);
    const overId = over?.dataset.id;
    if (!overId || overId === dragging) return;
    const next = order.filter((id) => id !== dragging);
    const r = over!.getBoundingClientRect();
    next.splice(next.indexOf(overId) + (ev.clientY > r.top + r.height / 2 ? 1 : 0), 0, dragging);
    if (next.join() !== order.join()) order = next;
  }
  async function end() {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    const was = items.map((x) => x.id).join(), now = order;
    dragging = null;
    if (now && now.join() !== was) await onreorder(now);
    order = null;
  }
  async function key(ev: KeyboardEvent, id: string) {
    if (disabled || (ev.key !== "ArrowUp" && ev.key !== "ArrowDown")) return;
    ev.preventDefault();
    const ids = items.map((x) => x.id);
    const i = ids.indexOf(id), j = i + (ev.key === "ArrowUp" ? -1 : 1);
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    await onreorder(ids);
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`li[data-sort="${group}"][data-id="${id}"] .grip`)?.focus());
  }
</script>

<ul class="sortable">
  {#each shown as item (item.id)}
    <li data-sort={group} data-id={item.id} class:dragging={dragging === item.id}>
      {#if !disabled && items.length > 1}
        <span class="grip" role="button" tabindex="0" aria-label="Drag to reorder (or use the arrow keys)"
              title="Drag to reorder" onpointerdown={(ev) => start(ev, item.id)} onkeydown={(ev) => key(ev, item.id)}>⠿</span>
      {/if}
      <div class="body">{@render row(item)}</div>
    </li>
  {/each}
</ul>

<style>
  .sortable { list-style: none; margin: 0; padding: 0; }
  li { display: flex; gap: 0.35rem; align-items: flex-start; }
  li.dragging { opacity: 0.6; background: var(--panel); border-radius: 4px; }
  .grip { cursor: grab; color: var(--ink-soft); padding: 0.1rem 0.15rem; user-select: none; touch-action: none; line-height: 1.4; }
  .grip:focus-visible { outline: 2px solid var(--accent); border-radius: 3px; }
  .body { flex: 1; min-width: 0; }
</style>
