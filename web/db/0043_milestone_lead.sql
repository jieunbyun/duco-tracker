-- 0043_milestone_lead.sql — a public milestone of a shared project can name a
-- lead: one of the people on the project (a member, or you). It is a label
-- only: everyone on the project still edits the milestone. Anyone there may
-- set or change it; the existing policy covers the new column. Safe to re-run.
alter table group_milestone add column if not exists lead_id uuid references auth.users on delete set null;
