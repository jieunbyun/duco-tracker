-- 0072_tidy_follow.sql — a small task's follow-on: another small task, with a name of its own,
-- on the same day or another, that goes with it. Run after 0058_tidy.sql.
--
-- follows   the small task this one follows on from. A task and its follow-ons (and theirs)
--           move together: moving one moves the others not yet ticked by as many days.
--           Deleting one in the middle joins the one after to the one before (done by the app);
--           otherwise the link just goes (on delete set null).
--
-- Safe to re-run.
alter table tidy add column if not exists follows uuid references tidy on delete set null;
create index if not exists tidy_follows on tidy (follows);
