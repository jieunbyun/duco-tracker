-- 0039_reading_quotes.sql — a reading's note can be a quote (the words as
-- written, with a page) with your note on it attached, or a note on its own.
-- One of the two is always there. Safe to re-run.
alter table reading_note add column if not exists quote text;
alter table reading_note alter column body drop not null;
alter table reading_note drop constraint if exists reading_note_quote_or_note;
alter table reading_note add constraint reading_note_quote_or_note
  check (coalesce(btrim(quote), '') <> '' or coalesce(btrim(body), '') <> '');
create index if not exists reading_note_quotes_idx on reading_note (user_id, noted_on) where quote is not null;
