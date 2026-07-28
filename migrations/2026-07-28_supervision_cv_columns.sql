-- Supervision CV entries need three atoms the generic cv_entry table lacks:
-- the student's degree/level, and a start/end date range (entry_date is a
-- single date). Run once in the Supabase SQL editor. Safe to re-run.
alter table cv_entry
    add column if not exists student_level text,
    add column if not exists start_on      date,
    add column if not exists end_on        date;
