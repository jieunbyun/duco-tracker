-- 0067_exp_innovation.sql — Experiments: a note can also be tagged Innovation.
-- Safe to re-run.
alter table exp_note drop constraint if exists exp_note_tags_check;
alter table exp_note add constraint exp_note_tags_check
  check (cardinality(tags) >= 1 and tags <@ array['tip', 'hypothesis', 'practice', 'self', 'innovation']);
