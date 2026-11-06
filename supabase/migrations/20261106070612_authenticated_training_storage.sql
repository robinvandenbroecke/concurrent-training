-- Browser storage is separate from the private research/admin API schema.
create table public.ct_training_accounts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  state jsonb not null default '{}'::jsonb,
  revision bigint not null default 1 check (revision > 0),
  updated_at timestamptz not null default now(),
  constraint account_state_object check (jsonb_typeof(state) = 'object' and octet_length(state::text) <= 5000000)
);
create table public.ct_training_sessions (
  user_id uuid not null references auth.users(id) on delete cascade,
  id text not null check (length(id) between 1 and 128),
  payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key (user_id, id),
  constraint session_payload_object check (
    jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 1000000
    and payload ?& array['id','date','type','title','durationMinutes']
    and jsonb_typeof(payload->'id') = 'string' and payload->>'id' = id
    and jsonb_typeof(payload->'date') = 'string'
    and jsonb_typeof(payload->'type') = 'string'
    and payload->>'type' in ('kracht','duur')
    and jsonb_typeof(payload->'title') = 'string'
    and payload->>'date' ~ '^\d{4}-\d{2}-\d{2}$'
    and jsonb_typeof(payload->'durationMinutes') = 'number'
    and (payload->>'durationMinutes')::numeric between 0 and 10080
  )
);
alter table public.ct_training_accounts enable row level security;
alter table public.ct_training_sessions enable row level security;
revoke all on public.ct_training_accounts, public.ct_training_sessions from public, anon, authenticated;
grant select, insert, update on public.ct_training_accounts to authenticated;
-- Completed sessions are append-only. Retrying uses the same (user_id,id).
grant select, insert on public.ct_training_sessions to authenticated;
create policy account_read on public.ct_training_accounts for select to authenticated using ((select auth.uid()) = user_id);
create policy account_insert on public.ct_training_accounts for insert to authenticated with check ((select auth.uid()) = user_id);
create policy account_update on public.ct_training_accounts for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy session_read on public.ct_training_sessions for select to authenticated using ((select auth.uid()) = user_id);
create policy session_insert on public.ct_training_sessions for insert to authenticated with check ((select auth.uid()) = user_id);
create function public.ct_training_account_revision() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  new.revision := old.revision + 1;
  new.updated_at := pg_catalog.clock_timestamp();
  return new;
end;
$$;
revoke all on function public.ct_training_account_revision() from public, anon, authenticated;
create trigger ct_training_account_revision before update on public.ct_training_accounts
for each row execute function public.ct_training_account_revision();
notify pgrst, 'reload schema';
