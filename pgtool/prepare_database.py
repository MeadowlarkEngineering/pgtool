"""
Attempts to create teh database and perform the migrations if they do not exist
Requires an administrative user to create the databases
Runs migrations for each database in the migrations directory
"""
import sys
import os
import argparse
from urllib.parse import urlparse
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

    prepare(user, password, server, args.db_name_suffix, args.migrations_path)

def prepare(user, password, host, db_name_suffix = None, migration_path = 'migrations'):
    """
    Prepare all databases in the migrations folder
    """

    admin_dsn = f"postgres://{user}:{password}@{host}/postgres"
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

        print(f"Applying migrations in {database_path}")
        migrations = read_migrations(str(database_path))
    
        db_url = f"postgres://{user}:{password}@{host}/{db_name}"
        backend = get_backend(db_url)

        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))

if __name__ == "__main__":
    main()