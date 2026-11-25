-- 0077_pw_milestone.sql — a single milestone of a Planning project on Pathways, rather than the
-- whole project: the item takes the milestone's name and dates (moving it moves the milestone), and
-- goes when the milestone is deleted. Run after 0010_pathways.sql. Safe to re-run.
alter table pw_node add column if not exists milestone_id uuid references milestone on delete cascade;
