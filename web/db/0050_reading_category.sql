-- 0050_reading_category.sql — a reading can have a category of your own, to classify
-- journals and books. And no more PDFs are stored here: a reading links to OneDrive
-- or a web page, so the storage rules that let files in go. Copies stored earlier
-- can still be opened and removed. Safe to re-run.
alter table reading add column if not exists category text;

do $$
begin
  drop policy if exists "reading pdfs: own folder, add" on storage.objects;
  drop policy if exists "reading pdfs: own folder, replace" on storage.objects;
exception when insufficient_privilege then
  raise notice 'Could not change the storage rules; the app has no way to upload anyway.';
end $$;
