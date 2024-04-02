
from textwrap import dedent
from pathlib import Path
import argparse
from datetime import datetime

migration_template = dedent(
    '''\
    """
    {message}
    """
    from yoyo import step

    steps = [
        step('rollup_sql', 'rollback_sql')
    ]
    '''
)

def generate_filename(message):
    now = datetime.now()
    prefix = now.strftime('%Y-%m-%d-%H-%M-%S')
    sanitized_message = message.replace(' ', '-').lower()
    return f"{prefix}-{sanitized_message}.py"

def main():
    parser = argparse.ArgumentParser(description="Create a new migration in the specified migration directory")
    parser.add_argument('--database', required=True, help="Database Migration Directory")
    parser.add_argument('message', help="Migration Message")

    args = parser.parse_args()

    filename = generate_filename(args.message)
    path = Path('migrations') / args.database 

    if not path.exists():
        print(f"Path {path} does not exist. Creating it now.")
        path.mkdir(parents=True)

    full_path = path / filename
    with open(full_path, 'w') as f:
        print(f"Creating migration {full_path}")
        f.write(migration_template.format(message=args.message))


if __name__ == "__main__":
    main()