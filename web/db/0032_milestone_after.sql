-- 0032_milestone_after.sql — a milestone can come after others in its project:
-- with no start date of its own, it starts when the last of them is due (and one
-- with no due date is due when the first milestone after it starts). Safe to re-run.
alter table milestone add column if not exists after_ids uuid[] not null default '{}';
