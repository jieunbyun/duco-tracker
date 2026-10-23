-- 0033_slot_sync_cancel.sql — remember who cancelled a sitting. The Outlook sync
-- strikes through a kept event that has gone from Outlook, and restores it if it
-- comes back; a sitting you cancel yourself must stay cancelled. Until now the
-- sync could not tell the two apart, so every sitting you cancelled on an
-- Outlook event came back at the next sync. Existing cancelled sittings count
-- as yours, so none is restored. Safe to re-run.
alter table todo_slot add column if not exists cancelled_by_sync boolean not null default false;
