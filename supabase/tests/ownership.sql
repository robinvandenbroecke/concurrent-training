-- Disposable fixtures only: every statement is rolled back, including users.
begin;
select set_config('ct_test.alice', gen_random_uuid()::text, true);
select set_config('ct_test.bob', gen_random_uuid()::text, true);
insert into auth.users(id) values (current_setting('ct_test.alice')::uuid),(current_setting('ct_test.bob')::uuid);
set local role authenticated;
select set_config('request.jwt.claim.sub',current_setting('ct_test.alice'),true);
insert into public.ct_training_accounts(user_id,state) values (auth.uid(),'{"ct_profile":{"name":"RLS fixture"}}');
insert into public.ct_training_sessions(user_id,id,payload) values (auth.uid(),'rls-fixture','{"id":"rls-fixture","date":"2026-11-06","type":"kracht","title":"RLS fixture","durationMinutes":30}');
-- Owner can read and update; revision comes from the database, not the client.
do $$ begin
  assert (select count(*) from public.ct_training_sessions)=1, 'own session missing';
  update public.ct_training_accounts set state='{}',revision=999 where user_id=auth.uid() and revision=1;
  assert (select revision from public.ct_training_accounts)=2, 'revision not managed by server';
  update public.ct_training_accounts set state='{"stale":true}' where user_id=auth.uid() and revision=1;
  assert not found, 'stale state overwrote current state';
  begin
    update public.ct_training_accounts set user_id=current_setting('ct_test.bob')::uuid where user_id=auth.uid();
    raise exception 'ownership transfer was allowed';
  exception when insufficient_privilege then null; end;
  begin
    insert into public.ct_training_sessions(user_id,id,payload) values (current_setting('ct_test.bob')::uuid,'forged','{"id":"forged","date":"2026-11-06","type":"duur","title":"forged","durationMinutes":1}');
    raise exception 'forged owner was allowed';
  exception when insufficient_privilege then null; end;
  begin
    update public.ct_training_sessions set payload='{}' where user_id=auth.uid();
    raise exception 'completed session update was allowed';
  exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub',current_setting('ct_test.bob'),true);
do $$ begin
  assert (select count(*) from public.ct_training_sessions)=0, 'another user can read sessions';
  assert (select count(*) from public.ct_training_accounts)=0, 'another user can read account';
  update public.ct_training_accounts set state='{}' where user_id=current_setting('ct_test.alice')::uuid;
  assert not found, 'another user can update account';
  -- IDs belong to a user; the same client ID is safe for another owner.
  insert into public.ct_training_sessions(user_id,id,payload) values (auth.uid(),'rls-fixture','{"id":"rls-fixture","date":"2026-11-06","type":"duur","title":"B fixture","durationMinutes":1}');
  assert (select count(*) from public.ct_training_sessions)=1;
end $$;
set local role anon;
do $$ begin
  begin
    perform 1 from public.ct_training_sessions;
    raise exception 'anonymous session read was allowed';
  exception when insufficient_privilege then null; end;
  begin
    perform 1 from public.ct_training_accounts;
    raise exception 'anonymous account read was allowed';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
rollback;
