// "See what they see": while set, the app shows a member's tabs as they see
// them, read-only. Only the supervisor can start it (from the Members tab).
import type { Member } from "./group";

export const preview = $state({ as: null as Member | null });
