-- 0079_exp_teaching.sql — Experiments: notes, topics and subtopics can also be tagged Teaching.
-- Run after 0069_exp_modelling.sql. Safe to re-run.
alter table exp_note drop constraint if exists exp_note_tags_check;
alter table exp_note add constraint exp_note_tags_check
  check (cardinality(tags) >= 1 and tags <@ array['tip', 'hypothesis', 'practice', 'self', 'innovation', 'modelling', 'teaching']);

alter table exp_topic drop constraint if exists exp_topic_tags_check;
alter table exp_topic add constraint exp_topic_tags_check
  check (tags <@ array['tip', 'hypothesis', 'practice', 'self', 'innovation', 'modelling', 'teaching']);
