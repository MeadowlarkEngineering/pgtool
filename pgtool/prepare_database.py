"""
Attempts to create teh database and perform the migrations if they do not exist
Requires an administrative user to create the databases
Runs migrations for each database in the migrations directory
"""
import sys
import os
import argparse
from urllib.parse import urlparse, quote
from pathlib import Path
from pgtool.utilities import db_exists, get_connection
from yoyo import read_migrations, get_backend


def main():
    """
    Create database and run migrations
    """

    parser = argparse.ArgumentParser(description="Prepare database and run migrations")
    parser.add_argument("db_url", nargs='?', help="Database URL (If not provided will use DB_URL environment variable)")
    parser.add_argument("--db-name-suffix", help="Adds a suffix to the database name separated by an underscore")
    parser.add_argument("--migrations-path", help="Path to the migrations directory", default="migrations")
    parser.add_argument("--rollback", type=int, help="Rollback N migrations. Use 0 to list available", default=None)

    args = parser.parse_args()

    if args.db_url:
        db_url = args.db_url
    else:
        db_url = os.environ.get('DB_URL', None)

    if db_url is None:
        print("DB_URL must be set or specified on command line")
        exit(1)

    url = urlparse(db_url)

    server = url.hostname
    user = url.username
    password = url.password

    prepare(user, password, server, args.db_name_suffix, args.migrations_path, args.rollback)

def prepare(user, password, host, db_name_suffix = None, migration_path = 'migrations', rollback=None):
    """
    Prepare all databases in the migrations folder
    """

    admin_dsn = f"postgres://{user}:{quote(password)}@{host}/postgres"
    migration_path = Path(migration_path)

    for database_path in migration_path.glob('*'):
    
        db_name = database_path.name
        if db_name_suffix is not None:
            db_name = f"{db_name}_{db_name_suffix}"
    
        print(f"Processing database {db_name}")
        # Create database if it does not exist
        if not db_exists(db_name, dsn=admin_dsn):
            print(f"Database {db_name} does not exist. Creating it now.")
            conn = get_connection(admin_dsn, transactional=False)
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE {db_name}")
            conn.close()

        db_url = f"postgres://{user}:{password}@{host}/{db_name}"
        backend = get_backend(db_url)


        migrations = read_migrations(str(database_path))

        with backend.lock():
            if rollback is not None:
                available = backend.to_rollback(migrations)
                rollback_n = rollback
                if len(available) < rollback_n:
                    return{"error": "Unable to rollback that far. Use --rollback 0 to see available rollback"}

                if rollback_n == 0:
                    print(f"Available migrations to rollback in {database_path}")
                    for i, m in enumerate(available):
                        print(f"{i+1}: {m.path}")
                    return {"rollback_migrations": [{i+1: m.path} for i, m in enumerate(available)]}
                else:
                    backend.rollback_migrations(available[:rollback_n])
                    return 
            else:
                print(f"Applying migrations in {database_path}")
    
                to_apply = backend.to_apply(migrations) 
                backend.apply_migrations(backend.to_apply(migrations))
                return {"applied_migrations": [{i+1: m.path} for i, m in enumerate(to_apply)]}

if __name__ == "__main__":
    main()