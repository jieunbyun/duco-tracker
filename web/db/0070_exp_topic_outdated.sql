-- 0070_exp_topic_outdated.sql — Experiments: a topic or subtopic can be marked outdated
-- too, like a note (⊘): it stays where it is, in grey, with everything under it.
-- Safe to re-run.
alter table exp_topic add column if not exists outdated boolean not null default false;
