// Which shared projects you keep minimised, in Projects and the Logbook alike: each
// person's own, kept with their account so it lasts to the next log-on (0046).
import { loadMinimised, setMinimised } from "./group";

export class Minimised {
  ids = $state(new Set<string>());
  // `saved` is false while previewing: it then only folds them on screen,
  // since what a member keeps minimised is theirs
  constructor(private saved: () => boolean) {}

  has(id: string) {
    return this.ids.has(id);
  }
  async load() {
    if (this.saved()) this.ids = await loadMinimised();
  }
  private set(id: string, on: boolean) {
    const s = new Set(this.ids);
    if (on) s.add(id);
    else s.delete(id);
    this.ids = s;
  }
  /** Fold or open it at once; if that cannot be saved, it goes back and this throws. */
  async toggle(id: string) {
    const on = !this.ids.has(id);
    this.set(id, on);
    if (!this.saved()) return;
    try {
      await setMinimised(id, on);
    } catch (e) {
      this.set(id, !on);
      throw e;
    }
  }
}
