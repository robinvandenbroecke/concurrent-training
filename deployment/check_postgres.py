"""CI-only integration check against a disposable PostgreSQL service.

Exercises migrations in a private schema, including an encoded password, and
checks that retrying startup keeps data and leaves existing public tables alone.
"""
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from deployment.serve import SCHEMA, prepare_database


def main():
    # This is a disposable CI login, never a production connection or secret.
    original = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(original)
    with admin.begin() as conn:
        conn.execute(text("create table public.hosting_ci_control (id integer primary key)"))
        conn.execute(text("insert into public.hosting_ci_control values (7)"))
        conn.execute(text("create role ct_hosting_ci login password 'ci%encoded@password'"))
        conn.execute(text(f'create schema "{SCHEMA}" authorization ct_hosting_ci'))
        for role in ("anon", "authenticated"):
            conn.execute(text(f'create role "{role}"'))
            conn.execute(text(f'grant usage on schema "{SCHEMA}" to "{role}"'))
    url = original.set(username="ct_hosting_ci", password="ci%encoded@password").update_query_dict({"options": f"-csearch_path={SCHEMA}"})
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["AUTO_CREATE_TABLES"] = "false"
    prepare_database(url)
    private = create_engine(url)
    with private.begin() as conn:
        assert conn.execute(text("select current_schema()")).scalar() == SCHEMA
        assert conn.execute(text("select version_num from alembic_version")).scalar() == "006"
        conn.execute(text("insert into athletes (name, owner_subject) values ('CI retained athlete', 'ci')"))
    prepare_database(url)
    with private.connect() as conn:
        assert conn.execute(text("select count(*) from athletes")).scalar() == 1
        assert len(inspect(conn).get_table_names()) >= 12
    with admin.connect() as conn:
        assert conn.execute(text("select id from public.hosting_ci_control")).scalar() == 7
        assert not conn.execute(text("select has_schema_privilege('anon', :schema, 'usage')"), {"schema": SCHEMA}).scalar()
        assert not conn.execute(text("select has_schema_privilege('authenticated', :schema, 'usage')"), {"schema": SCHEMA}).scalar()
        assert conn.execute(text("select bool_and(rowsecurity) from pg_tables where schemaname=:schema"), {"schema": SCHEMA}).scalar()
    private.dispose()
    admin.dispose()
    print("Private hosting schema, encoded credentials, data retention and Data API isolation verified")


if __name__ == "__main__":
    main()
