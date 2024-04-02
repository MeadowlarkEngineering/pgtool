import argparse
import pathlib
from dotenv import dotenv_values
from yoyo import read_migrations
from yoyo import get_backend
import logging
logging.basicConfig(encoding='utf-8',format='%(levelname)s: %(message)s', level=logging.INFO)

DB_URL='DB_URL'
DB_DSN='DB_DSN'

def main():
    
    parser = argparse.ArgumentParser(description="Database Migrator")
    parser.add_argument('database', help="The database migrations to load")
    parser.add_argument('--environment', required=True, help="Indicates which .env to load to connect")
    parser.add_argument('--list', '-l', action='store_true', help="List migrations and exit")
    
    # By specifying nargs=1 and a default, if --rollback is present then args.rollback is a list
    # but if --rollback is not present, then args.rollback is the default.
    # Super hacky, but this is used below to determine if rollback is requested
    parser.add_argument('--rollback', nargs=1, type=int, help="Rollback N migrations. Use 0 to list available")
    
    args = parser.parse_args()
    
    envfile = f".env.{args.database}.{args.environment}"
    if not pathlib.Path(envfile).exists():
        logging.error(f"Cannot locate file {envfile}")
        exit(1)

    values = dotenv_values(envfile)
    
    if DB_DSN in values:
        backend = get_backend(values[DB_DSN])
    elif DB_URL in values:
        backend = get_backend(values[DB_URL])
    else:
        logging.error(f"database connection url {DB_URL} or {DB_DSN} must be defined in {envfile}")
        exit(1)

    migrations = read_migrations(f"./migrations/{args.database}")

    if args.list:
        for i,m in enumerate(migrations):
            print(i+1, m.path)
        exit(0)

    with backend.lock():
    
        if args.rollback is not None:
            available = backend.to_rollback(migrations)
            rollback_n = args.rollback[0]
            if len(available) < rollback_n:
                logging.info("Unable to rollback that far. Use --rollback 0 to see available rollback")

            if rollback_n == 0:
                for i, m in enumerate(available):
                    print(i+1, m.path)
            else:
                backend.rollback_migrations(available[:rollback_n])
        else:
            # Apply any outstanding migrations
            backend.apply_migrations(backend.to_apply(migrations))


if __name__ == "__main__":
    main()