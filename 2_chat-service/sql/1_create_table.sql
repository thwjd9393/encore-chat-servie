drop table if exists messages;
drop table if exists conversations;
drop table if exists users;

create extension if not exists "pgcrypto";

create table if not exists profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    username varchar(30) not null,
    created_at timestamptz not null default now()
);

create table if not exists conversations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references profiles(id) on delete cascade,
    title varchar(100),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations(id) on delete cascade,
    role varchar(20) not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_conversations_user_id on conversations(user_id);
create index if not exists idx_messages_conversation_id on messages(conversation_id);