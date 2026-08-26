create extension if not exists "pgcrypto";

create table users (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    username varchar(30) not null check (length(username) >= 2),
    created_at timestamptz not null default now()
);


//컬럼 정의서용
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_name = 'users' and table_schema = 'public'
order by ordinal_position;

// like 연산자는 성능에 관계가 있음. 조심해서 쓰기
select email, username from users
where email like '%e%';

//