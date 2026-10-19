// Reading meeting invites from .ics (iCalendar) files: an invite attachment or
// a calendar export. Returns the timed meetings that fall within a date range,
// as wall-clock times in this browser's time zone — the diary's own clock.
//
// Covers what invites actually use: UTC or zoned start times (IANA names and
// Outlook's Windows names), DTEND or DURATION, daily/weekly RRULEs with
// INTERVAL/COUNT/UNTIL/BYDAY, EXDATE, moved occurrences (RECURRENCE-ID) and
// cancellations. All-day events are skipped unless asked for (opts.allDay).

export type Meeting = {
  uid: string;
  title: string;
  date: string; // YYYY-MM-DD, local
  start: string; // HH:MM, local
  end: string; // HH:MM, local
  location: string;
  /** stable identity of this occurrence across syncs: the event's UID, plus
   *  the original start for one occurrence of a repeating event */
  key: string;
  allDay: boolean; // date only; start and end are ""
  free: boolean; // shown as Free in Outlook (often a reminder or deadline)
  tentative: boolean; // shown as Tentative, or an invitation not yet accepted
};

const WINDOWS_ZONES: Record<string, string> = {
  "GMT Standard Time": "Europe/London",
  "Greenwich Standard Time": "Atlantic/Reykjavik",
  "W. Europe Standard Time": "Europe/Berlin",
  "Romance Standard Time": "Europe/Paris",
  "Central Europe Standard Time": "Europe/Budapest",
  "Central European Standard Time": "Europe/Warsaw",
  "E. Europe Standard Time": "Europe/Chisinau",
  "FLE Standard Time": "Europe/Kiev",
  "GTB Standard Time": "Europe/Bucharest",
  "Eastern Standard Time": "America/New_York",
  "Central Standard Time": "America/Chicago",
  "Mountain Standard Time": "America/Denver",
  "Pacific Standard Time": "America/Los_Angeles",
  "Korea Standard Time": "Asia/Seoul",
  "China Standard Time": "Asia/Shanghai",
  "Tokyo Standard Time": "Asia/Tokyo",
  "Singapore Standard Time": "Asia/Singapore",
  "India Standard Time": "Asia/Kolkata",
  "AUS Eastern Standard Time": "Australia/Sydney",
  "UTC": "UTC",
  "Coordinated Universal Time": "UTC",
};

type Prop = { name: string; params: Record<string, string>; value: string };
type Wall = { y: number; mo: number; d: number; h: number; mi: number; s: number };
type Stamp = { wall: Wall; zone: string | null; utc: boolean; allDay: boolean };

function unfold(text: string): string[] {
  return text.replace(/\r\n/g, "\n").replace(/\n[ \t]/g, "").split("\n");
}

function parseProp(line: string): Prop | null {
  const colon = line.search(/:(?=(?:[^"]*"[^"]*")*[^"]*$)/);
  if (colon < 0) return null;
  const [name, ...paramParts] = line.slice(0, colon).split(";");
  const params: Record<string, string> = {};
  for (const p of paramParts) {
    const eq = p.indexOf("=");
    if (eq > 0) params[p.slice(0, eq).toUpperCase()] = p.slice(eq + 1).replace(/^"|"$/g, "");
  }
  return { name: name.toUpperCase(), params, value: line.slice(colon + 1) };
}

function unescapeText(v: string): string {
  return v.replace(/\\n/gi, " ").replace(/\\([,;\\])/g, "$1").trim();
}

function parseStamp(value: string, params: Record<string, string>): Stamp | null {
  const m = value.match(/^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?$/);
  if (!m) return null;
  const wall = { y: +m[1], mo: +m[2], d: +m[3], h: +(m[4] ?? 0), mi: +(m[5] ?? 0), s: +(m[6] ?? 0) };
  const zone = params.TZID ? resolveZone(params.TZID) : null;
  return { wall, zone, utc: !!m[7], allDay: !m[4] || params.VALUE === "DATE" };
}

function resolveZone(tzid: string): string | null {
  const name = WINDOWS_ZONES[tzid] ?? tzid.replace(/^\/.*?\//, "");
  try {
    new Intl.DateTimeFormat("en-GB", { timeZone: name });
    return name;
  } catch {
    return null; // unknown zone: read as the browser's own wall clock
  }
}

/** Offset (ms) of `zone` from UTC at the given instant. */
function zoneOffset(zone: string, instant: number): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date(instant));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second")) - instant;
}

/** The instant a wall-clock time in a zone denotes (null zone = this browser). */
function toInstant(w: Wall, zone: string | null, utc: boolean): number {
  const asUtc = Date.UTC(w.y, w.mo - 1, w.d, w.h, w.mi, w.s);
  if (utc) return asUtc;
  if (!zone) return new Date(w.y, w.mo - 1, w.d, w.h, w.mi, w.s).getTime();
  let t = asUtc - zoneOffset(zone, asUtc);
  t = asUtc - zoneOffset(zone, t); // second pass settles DST edges
  return t;
}

function addWallDays(w: Wall, n: number): Wall {
  const d = new Date(Date.UTC(w.y, w.mo - 1, w.d + n));
  return { ...w, y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate() };
}

const pad = (n: number) => String(n).padStart(2, "0");
function localParts(instant: number): { date: string; time: string } {
  const d = new Date(instant);
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
}

function durationMs(v: string): number {
  const m = v.match(/^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/);
  if (!m) return 0;
  const ms = ((+(m[2] ?? 0) * 7 + +(m[3] ?? 0)) * 86400 + +(m[4] ?? 0) * 3600 + +(m[5] ?? 0) * 60 + +(m[6] ?? 0)) * 1000;
  return m[1] === "-" ? -ms : ms;
}

const DAY_CODES = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];

type VEvent = { props: Prop[] };

function get(e: VEvent, name: string): Prop | undefined {
  return e.props.find((p) => p.name === name);
}

/** Wall-clock starts of a recurring series, up to `untilInstant`. */
function* occurrences(start: Stamp, rrule: string, untilInstant: number): Generator<Wall> {
  const rule = Object.fromEntries(rrule.split(";").map((kv) => kv.split("=")).map(([k, v]) => [k.toUpperCase(), v]));
  const freq = rule.FREQ;
  const interval = Math.max(1, Number(rule.INTERVAL ?? 1));
  const count = rule.COUNT ? Number(rule.COUNT) : Infinity;
  const until = rule.UNTIL ? parseStamp(rule.UNTIL, {}) : null;
  const untilAt = until ? toInstant(until.wall, until.utc ? null : start.zone, until.utc) : Infinity;
  if (freq !== "DAILY" && freq !== "WEEKLY") {
    yield start.wall; // other frequencies: the first occurrence only
    return;
  }
  const byDay = (rule.BYDAY ?? "").split(",").filter(Boolean).map((c: string) => DAY_CODES.indexOf(c.slice(-2)));
  let emitted = 0;
  for (let i = 0; i < 3660 && emitted < count; i++) {
    const w = addWallDays(start.wall, i);
    const dow = new Date(Date.UTC(w.y, w.mo - 1, w.d)).getUTCDay();
    let hit: boolean;
    if (freq === "DAILY") {
      hit = i % interval === 0;
    } else {
      const week = Math.floor(i / 7); // weeks counted from the series start
      const days = byDay.length ? byDay : [new Date(Date.UTC(start.wall.y, start.wall.mo - 1, start.wall.d)).getUTCDay()];
      hit = week % interval === 0 && days.includes(dow);
    }
    if (!hit) continue;
    const at = toInstant(w, start.zone, start.utc);
    if (at > untilAt || at > untilInstant) return;
    emitted += 1;
    yield w;
  }
}

/** Timed meetings from an .ics text whose start falls on a day in [from, to]. */
export function meetingsInRange(text: string, from: string, to: string, opts: { allDay?: boolean } = {}): Meeting[] {
  const events: VEvent[] = [];
  let current: VEvent | null = null;
  for (const line of unfold(text)) {
    if (/^BEGIN:VEVENT$/i.test(line)) current = { props: [] };
    else if (/^END:VEVENT$/i.test(line)) { if (current) events.push(current); current = null; }
    else if (current) { const p = parseProp(line); if (p) current.props.push(p); }
  }

  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  const rangeEnd = new Date(ty, tm - 1, td + 1).getTime();
  const rangeStart = new Date(fy, fm - 1, fd).getTime();

  // Moved or cancelled single occurrences, keyed by uid + original start.
  const overrides = new Map<string, VEvent>();
  for (const e of events) {
    const rid = get(e, "RECURRENCE-ID");
    const uid = get(e, "UID")?.value ?? "";
    if (!rid) continue;
    const s = parseStamp(rid.value, rid.params);
    if (s) overrides.set(`${uid}@${toInstant(s.wall, s.zone, s.utc)}`, e);
  }

  const out: Meeting[] = [];
  const emit = (e: VEvent, startAt: number, lengthMs: number, key: string, allDay: boolean) => {
    if (get(e, "STATUS")?.value.toUpperCase() === "CANCELLED") return;
    if (startAt < rangeStart || startAt >= rangeEnd) return;
    const s = localParts(startAt);
    const endAt = startAt + Math.max(lengthMs, 0);
    const en = localParts(endAt);
    const busy = (get(e, "X-MICROSOFT-CDO-BUSYSTATUS")?.value ?? "").toUpperCase();
    out.push({
      uid: get(e, "UID")?.value ?? "",
      title: unescapeText(get(e, "SUMMARY")?.value ?? "(no title)"),
      date: s.date,
      start: allDay ? "" : s.time,
      // a meeting that runs past midnight is cut at the end of its day
      end: allDay ? "" : en.date === s.date && en.time > s.time ? en.time : "23:59",
      location: unescapeText(get(e, "LOCATION")?.value ?? ""),
      key,
      allDay,
      free: busy === "FREE" || (get(e, "TRANSP")?.value ?? "").toUpperCase() === "TRANSPARENT",
      tentative: busy === "TENTATIVE" || (get(e, "STATUS")?.value ?? "").toUpperCase() === "TENTATIVE",
    });
  };

  for (const e of events) {
    if (get(e, "RECURRENCE-ID")) continue; // handled as overrides
    const dt = get(e, "DTSTART");
    const start = dt && parseStamp(dt.value, dt.params);
    if (!start || (start.allDay && !opts.allDay)) continue;
    const startAt = toInstant(start.wall, start.zone, start.utc);
    const dtEnd = get(e, "DTEND");
    const end = dtEnd && parseStamp(dtEnd.value, dtEnd.params);
    const lengthMs = end
      ? toInstant(end.wall, end.zone, end.utc) - startAt
      : durationMs(get(e, "DURATION")?.value ?? "PT1H");
    const uid = get(e, "UID")?.value ?? "";
    const rrule = get(e, "RRULE")?.value;
    if (!rrule) {
      emit(e, startAt, lengthMs, uid || `${get(e, "SUMMARY")?.value ?? ""}|${startAt}`, start.allDay);
      continue;
    }
    const excluded = new Set<number>();
    for (const ex of e.props.filter((p) => p.name === "EXDATE")) {
      for (const v of ex.value.split(",")) {
        const s = parseStamp(v, ex.params);
        if (s) excluded.add(toInstant(s.wall, s.zone ?? start.zone, s.utc));
      }
    }
    for (const w of occurrences(start, rrule, rangeEnd)) {
      const at = toInstant(w, start.zone, start.utc);
      if (excluded.has(at)) continue;
      const moved = overrides.get(`${uid}@${at}`);
      const key = `${uid}|${new Date(at).toISOString()}`;
      if (moved) {
        const ms = get(moved, "DTSTART");
        const me = get(moved, "DTEND");
        const s = ms && parseStamp(ms.value, ms.params);
        if (!s) continue;
        const sAt = toInstant(s.wall, s.zone, s.utc);
        const eStamp = me && parseStamp(me.value, me.params);
        emit(moved, sAt, eStamp ? toInstant(eStamp.wall, eStamp.zone, eStamp.utc) - sAt : lengthMs, key, s.allDay);
      } else {
        emit(e, at, lengthMs, key, start.allDay);
      }
    }
  }
  return out.sort((a, b) => (a.date + a.start).localeCompare(b.date + b.start));
}

/** Every UID+occurrence key in a calendar, for telling "not in range" from "gone". */
export function eventUids(text: string): Set<string> {
  const uids = new Set<string>();
  for (const line of unfold(text)) {
    const m = line.match(/^UID[:;](?:.*:)?(.*)$/i);
    if (m) uids.add(m[1].trim());
  }
  return uids;
}
