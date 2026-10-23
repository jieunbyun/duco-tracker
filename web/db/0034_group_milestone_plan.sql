-- 0034_group_milestone_plan.sql — a member's project milestones are set the way
-- your Planning milestones are: a start and a due date (to the day), what each
-- comes after (with no start date of its own, it starts when the last of those
-- is due; with no due date, it is due when the first one after it starts), a
-- hard deadline, and notes. Existing milestones keep their due date and gain
-- nothing else. The existing policy (you, and the people on the project) covers
-- the new columns. Safe to re-run.
alter table group_milestone add column if not exists start_on      date;
alter table group_milestone add column if not exists hard_deadline boolean not null default false;
alter table group_milestone add column if not exists notes         text;
alter table group_milestone add column if not exists after_ids     uuid[] not null default '{}';
