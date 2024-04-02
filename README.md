# PG Tool

Author: jshapiro@meadowlarkengineering.com

Copyright (c) 2024 Meadowlark Engineering LLC

This repository contains the tools to quickly create and migrates databases. 

Recommended usage is to fork this repo and commit your database migrations directly 
to the forked repo.

## Quick References
**Install**
```
poetry install
```

**.env.\<database\>.\<environment\> File**
```
DB_URL=postgres://<admin_user>:<admin_password>@<db_host>/<database>
```

**Create a Database**
```
poetry run create-database --admin-password <admin password> \
    --ro-password <readonly password> \
    --rw-password <readwrite password> \
    <database> <environment>
```

**Run Migrations**
```
poetry run migrate-database --environment <environment> <database>
```

**Rollback a Migration**
```
poetry run migrate-database --environment <environment> --rollback <N> <database>
```

**Create a Migratino**
```
poetry run create-migration --database <database> "Add Table movies"
```

## Tutorial

### Start a postgresql database

If you have docker installed, then start a postgresql database with the command
```
docker run --name mydb -e POSTGRES_PASSWORD=secret -p 5432:5432 -d --rm postgres
```
This will start a postgres container named `mydb`.  The root username is `postgres` and 
the root password is `secret`

Set the appropriate environment variables ofr connecting to the database with db creation permisisons. e.g.
```
export PGUSER=postgres
export PGHOST=localhost
export PGPASSWORD=secret
export PGDATABASE=postgres
```

Confirm you can connect to the database instance by running `psql`

### Use pgtool to create a database
This package includes a script `create-database` that will bootstrap a database with three users: an admin user, 
a readonly user, and a readwrite user.  

Ensure that the environment is configured to connect to the database instance as the root user by setting 
the environment variables above, and then run 
```
poetry run create-database --admin-password x --ro-password y --rw-password z mydb dev
```

The create-database script expects two positional arguments, and three keyword arguments.
The two positional arguments are the database name and the environment, which must be one of `dev`, `test`, or `prod`.
The three keyword arguments are passwords for the admin, readonly, and readwrite user.

The name of the actual database is formed by joining the first and second positional arguments with an `_`. 

This command will create a new database within the database server named `mydb_dev`.  It will 
create three users named `mydb_dev_admin`, `mydb_dev_readonly`, and `mydb_dev_readwrite`.  The password
for each role is specified as a command line option. 

Confirm you can connect to the database as each user with the command
```
psql -U <username> -W mydb_dev
```

### Create a second database to serve as the test database
Best Practice is for developers to maintain development instances of the databases and for
the devops team to maintain test and staging instances of the database.  These can be maintained
on completely separate database servers, or within the same database server.  

Create a second database named `mydb_test` using the same command but with the new database name and different passwords

```
poetry run create-database --admin-password xTest --ro-password yTest --rw-password zTest mydb test
```

### Create .env files to specify connection urls
The `create-database` will write an environment file with a db connection variable into the current directory.
Store the connection URLs for the database in .env files in the root directory of the project.
These must never be checked into the git repository. 

Each .env file contains two suffixes, the database name, and the environment.

In our example, we are managing one database schema named `mydb` with two environments: `dev`and `test`.
Thus two .env files are created: `.env.mydb.dev` and `.env.mydb.test`. Each .env file declares 
an environment variable `DB_URL`. 

The contents of `.env.mydb.dev` will be 
```
DB_URL=postgres://mydb_dev_admin:x@localhost/mydb_dev
```

The contents of `.env.mydb.test` will be 
```
DB_URL=postgres://mydb_test_admin:xTest@localhost/mydb_test
```

### Run the Migrations
Database migrations are stored in this repository under the `migrations` directory.  Each unique database schema
has a subdirectory under migrations.  When running migrations you must specify 1) the database schema, (i.e. mydb) and 2) the environment.  This allows a developer to test migrations locally on a development database, and a devops team to apply migrations to a test or staging database prior to applying schema changes to a production database.

This repository currently has a single migration that adds a table named `tests` to the `mydb` database schema. 

Run this migration in the test environment with the command 
```
poetry run migrate-database --environment dev mydb
INFO: Applying 2023-02-03-08-42-32-add-table-tests
INFO:  - applying step 0
INFO: Marking 2023-02-03-08-42-32-add-table-tests applied
INFO: Applying 2023-02-03-08-42-53-add-column-to-tests
INFO:  - applying step 0
INFO: Marking 2023-02-03-08-42-53-add-column-to-tests applied
```

Run this same migration on the test environment with the command
```
poetry run migrate-database --environment test mydb
```

### Rollback the migration
It is often necessary to rollback a migration.  Migrations should include SQL that reverts the change
when possible.  Include the `--rollback [Steps]` option in the `migrate-database` command to rollback a migration

Make sure to specify the number of steps to roll back.  If you specify a rollback of 0, then it lists the available
steps possible to rollback.

```
poetry run migrate-database --environment test --rollback 1 mydb
```

This will produce the output:

> INFO: Rolling back 2023-02-03-08-42-53-add-column-to-tests
> INFO:  - rolling back step 0

### Create a new Migration

Create a new migration using the `create-migration` script:
```
poetry run create-migration --database mydb "Add Table movies"
```

This will create a new migration in the `migrations/mydb` directory. 

Change the step statement to 
```
    step('CREATE TABLE movies (id bigint primary key, name varchar(100))', 'DROP TABLE movies')
```

Run the migration 
```
poetry run migrate-database --environment test mydb
INFO: Applying 2023-02-03-08-48-34-add-table-movies
INFO:  - applying step 0
INFO: Marking 2023-02-03-08-48-34-add-table-movies applied      
```

Rollback the migration
```
poetry run migrate-database --environment test --rollback mydb
INFO: Rolling back 2023-02-03-08-48-34-add-table-movies
INFO:  - rolling back step 0
```