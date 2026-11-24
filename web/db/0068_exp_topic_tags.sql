-- 0068_exp_topic_tags.sql — Experiments: a topic or subtopic can carry tags too (none
-- needed), the same ones a note can. A topic's tags count for everything under it when
-- the tab shows one tag. Safe to re-run.
alter table exp_topic add column if not exists tags text[] not null default '{}';
alter table exp_topic drop constraint if exists exp_topic_tags_check;
alter table exp_topic add constraint exp_topic_tags_check
  check (tags <@ array['tip', 'hypothesis', 'practice', 'self', 'innovation']);
