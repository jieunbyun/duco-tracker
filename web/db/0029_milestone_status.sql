-- 0029_milestone_status.sql — a milestone is active, done or dropped: "planned"
-- added nothing for milestones. Those marked planned become active, and new
-- milestones start active. (Projects keep their own "planned".)
update milestone set status = 'active' where status = 'planned';
alter table milestone alter column status set default 'active';
alter table milestone drop constraint if exists milestone_status_check;
alter table milestone add constraint milestone_status_check check (status in ('active', 'done', 'dropped'));
