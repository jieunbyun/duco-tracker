<script lang="ts">
  // The hypotheses from Failures on a project or milestone, with the way there and back.
  import { onMount } from "svelte";
  import { toFailures } from "./failures";
  import type { Board, Failure, Attachment } from "./failures";
  import { fmtDay, today } from "./dates";

  type Props = {
    board: Board;
    items: Failure[]; // those on this project or milestone
    here: string; // the way back to it
    attach: Attachment; // what a new one is put on
    milestoneOf?: (f: Failure) => string | undefined; // on a project: which of its milestones
  };
  let { board, items, here, attach, milestoneOf }: Props = $props();

  let root = $state<HTMLElement>();
  const scope = () => root?.closest<HTMLElement>("[data-unsaved-scope]");

  // Going to Failures leaves behind what is typed in the project's and milestone's forms: ask first.
  onMount(() => {
    const el = scope();
    const typed = (ev: Event) => (ev.target as HTMLInputElement).form?.setAttribute("data-touched", "");
    const saved = (ev: Event) => (ev.target as HTMLFormElement).removeAttribute("data-touched");
    el?.addEventListener("input", typed);
    el?.addEventListener("submit", saved);
    return () => {
      el?.removeEventListener("input", typed);
      el?.removeEventListener("submit", saved);
    };
  });
  function go(to: string | Attachment) {
    if (scope()?.querySelector("form[data-touched]") && !confirm("Go to Failures without saving what you changed here?")) return;
    toFailures(here, to);
  }
  const themeOf = (f: Failure) => board.themes.find((t) => t.id === f.theme_id)?.name ?? "";
</script>

<div class="failure-list" bind:this={root}>
  <div class="head">
    <h4>Failures {#if items.length}<span>({items.length})</span>{/if}</h4>
    {#if !board.error}<button type="button" onclick={() => go(attach)}>+ Hypothesis ›</button>{/if}
  </div>
  {#if board.error}<p class="error">Could not load Failures: {board.error}</p>{/if}
  {#if items.length}
    <ul>
      {#each items as f (f.id)}
        {@const ms = milestoneOf?.(f)}
        <li>
          <div class="what">
            <p class="hypothesis">{f.hypothesis}</p>
            <p class="meta">
              {themeOf(f)}{ms ? ` · ${ms}` : ""} · created {fmtDay(f.created_on)}
              {#if f.due_on}· <span class:overdue={!f.lesson && f.due_on < today()}>deadline {fmtDay(f.due_on)}</span>{/if}
            </p>
            {#if f.lesson}<p class="lesson"><strong>Lesson:</strong> {f.lesson}</p>{/if}
          </div>
          <button type="button" onclick={() => go(f.id)}>Open in Failures ›</button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .failure-list { margin-top: 0.8rem; padding-top: 0.5rem; border-top: 1px dashed var(--rule); font-family: var(--font-ui); }
  .head { display: flex; gap: 0.6rem; align-items: baseline; }
  h4 { margin: 0; font-size: 0.85rem; font-weight: 600; color: var(--ink); }
  h4 span { font-weight: 400; color: var(--ink-soft); }
  button { font-size: 0.75rem; padding: 0.15rem 0.55rem; white-space: nowrap; }
  ul { list-style: none; margin: 0.2rem 0 0; padding: 0; }
  li { display: flex; flex-wrap: wrap; gap: 0.2rem 0.6rem; align-items: flex-start; padding: 0.35rem 0; }
  .what { flex: 1 1 14rem; min-width: 0; }
  p { margin: 0; overflow-wrap: anywhere; }
  .hypothesis { font-size: 0.85rem; color: var(--ink); white-space: pre-wrap; }
  .meta { font-size: 0.74rem; color: var(--ink-soft); }
  .lesson {
    font-size: 0.78rem; color: var(--ink-soft);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .overdue, .error { color: var(--danger); }
  .error { font-size: 0.78rem; }
</style>
