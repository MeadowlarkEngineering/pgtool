"""
Attempts to create teh database and perform the migrations if they do not exist
Requires an administrative user to create the databases
Runs migrations for each database in the migrations directory
"""
import sys
from urllib.parse import urlparse
from pathlib import Path
from pgtool.utilities import db_exists, get_connection
from yoyo import read_migrations, get_backend


def main():
    """
    Create database and run migrations
    """

    db_url = sys.argv[1]
    if db_url is None:
        print("DB_URL must be set")
        exit(1)

    url = urlparse(db_url)

    server = url.hostname
    user = url.username
    password = url.password

    admin_dsn = f"postgres://{user}:{password}@{server}/postgres"

    migration_path = Path('migrations')

    for database_path in migration_path.glob('*'):
        db_name = database_path.name
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
        backend = get_backend(db_url)

        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))

if __name__ == "__main__":
    main()