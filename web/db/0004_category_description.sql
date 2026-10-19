-- 0004_category_description.sql — a private note per category: what belongs
-- in it. Written in the app (Planning > Categories); the text lives only in
-- this database, behind the same owner-only rule as every other row.
alter table category add column if not exists description text;
