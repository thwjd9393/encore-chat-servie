alter table profiles enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;

drop policy if exists "select own profile" on profiles;
drop policy if exists "update own profile" on profiles;
drop policy if exists "select own conversations" on conversations;
drop policy if exists "insert own conversations" on conversations;
drop policy if exists "update own conversations" on conversations;
drop policy if exists "delete own conversations" on conversations;
drop policy if exists "select own messages" on messages;
drop policy if exists "insert own messages" on messages;

create policy "select own profile" on profiles
    for select using (auth.uid() = id);

create policy "update own profile" on profiles
    for update using (auth.uid() = id);

create policy "select own conversations" on conversations
    for select using (auth.uid() = user_id);

create policy "insert own conversations" on conversations
    for insert with check (auth.uid() = user_id);

create policy "update own conversations" on conversations
    for update using (auth.uid() = user_id);

create policy "delete own conversations" on conversations
    for delete using (auth.uid() = user_id);

create policy "select own messages" on messages
    for select using (
        exists (
            select 1 from conversations c
            where c.id = messages.conversation_id
              and c.user_id = auth.uid()
        )
    );

create policy "insert own messages" on messages
    for insert with check (
        exists (
            select 1 from conversations c
            where c.id = messages.conversation_id
              and c.user_id = auth.uid()
        )
    );


--테이블 생성 확인
select tablename, policyname, cmd
from pg_policies
where schemaname = 'public'
order by tablename, policyname;