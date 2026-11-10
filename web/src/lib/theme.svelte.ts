// Light or dark: follows the system until you choose, then keeps your choice
// (in this browser). index.html sets it before the page draws, so it never flashes.
type Theme = "light" | "dark";
const KEY = "theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");

function saved(): Theme | null {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}
const system = (): Theme => (media.matches ? "dark" : "light");

export const theme = $state({ value: saved() ?? system() });
const apply = () => (document.documentElement.dataset.theme = theme.value);
apply();

// until you choose, a change in the system's setting carries over
media.addEventListener("change", () => {
  if (saved()) return;
  theme.value = system();
  apply();
});

export function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
  apply();
  try { localStorage.setItem(KEY, theme.value); } catch { /* not kept: still switched for now */ }
}
