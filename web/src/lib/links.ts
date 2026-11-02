// Web addresses in free text (ideas, their notes, a to-do's note), so each can
// show as a short "link" instead of the whole address.

/** Text split around web addresses, so each address can show as a short "link". */
export function linkParts(text: string): { text?: string; url?: string }[] {
  const out: { text?: string; url?: string }[] = [];
  const re = /https?:\/\/[^\s<>"']+[^\s<>"'.,;:!?)\]]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    let url = m[0];
    // keep a closing bracket the address itself opened, e.g. …/Thing_(topic)
    const opens = (url.match(/\(/g) ?? []).length;
    const closes = (url.match(/\)/g) ?? []).length;
    if (opens > closes && text[m.index! + url.length] === ")") url += ")";
    if (m.index! > last) out.push({ text: text.slice(last, m.index) });
    out.push({ url });
    last = m.index! + url.length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}
