-- 0036_reading_milestone.sql — a reading can be tied to one of its project's
-- milestones as well as to the project. Deleting the milestone just unlinks
-- the reading. Safe to re-run.
alter table reading add column if not exists milestone_id uuid references milestone on delete set null;
