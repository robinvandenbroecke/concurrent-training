"""Exercise production RLS migration on the disposable PostgreSQL CI service.

Minimal auth stubs represent Supabase's documented auth.uid() contract. The
same ownership.sql is also run against the real Supabase schema before release.
"""
import os
from pathlib import Path
from sqlalchemy import create_engine


def main():
    engine = create_engine(os.environ['DATABASE_URL'])
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute('''
            create schema auth;
            create table auth.users (id uuid primary key);
            create function auth.uid() returns uuid language sql stable as $$
              select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid
            $$;
            grant usage on schema auth to authenticated, anon;
        ''')
        cursor.execute(Path('supabase/migrations/20261106070612_authenticated_training_storage.sql').read_text())
        raw.commit()
        cursor.execute(Path('supabase/tests/ownership.sql').read_text())
        raw.rollback()
        print('Cloud account ownership, anonymous denial, append-only sessions and stale revision rejection verified')
    finally:
        raw.close()
        engine.dispose()


if __name__ == '__main__':
    main()
