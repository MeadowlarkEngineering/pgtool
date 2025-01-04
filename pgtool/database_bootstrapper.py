"""
Initialize a new suite of databases for 1859
"""
import os
import argparse
from urllib.parse import urlparse
import psycopg2

class DatabaseBootstrapper:

    def __init__(self, dbname=None, environment = '', adminpw = None, ropw = None, rwpw = None, db_dsn=None):
        """
        Initialize the bootstrapper with the database name and environment
        @param {string} dbname the name of the database
        @param {string} environment the environment to create the database in

        If the environment is 'prod', then the database name is used as is
        Otherwise, the database name is suffixed with the environment name
        """
        self.dbname_no_env = dbname
        self.db_dsn = db_dsn
        self.environment = environment
        self.schema = f"public"
        self.admin_role = self.dbname + "_admin"
        self.ro_role = self.dbname + "_readonly"
        self.rw_role = self.dbname + "_readwrite"
        self.replication_role = self.dbname + "_replication"
        self.adminpw = adminpw
        self.ropw = ropw
        self.rwpw = rwpw
            
    @property
    def dbname(self):
        """
        Return the database name with the environment suffix
        """
        if self.dbname_no_env is None:
            connection_params = self.connection_params()
            dbname = connection_params.get("dbname", None)
        else:
            dbname = self.dbname_no_env

        if dbname is None:
            raise ValueError("Database name must be specified")
        
        if self.environment != '':
            return f"{dbname}_{self.environment}"
    
        return dbname

    def connection_params(self) -> dict:
        """
        Return the connection parameters for the database server administrator
        (i.e. someone with db create privileges)

        If db_dsn was specified during initialization, then use that
        Otherwise, use the environment variables
        """
        if self.db_dsn is not None:
            # Parse the dsn
            # If it is a postgres url, then extract the components
            # If it is a string of space separated key value pairs, then split it
            url = urlparse(self.db_dsn)
            if url.scheme in ['postgres', 'postgresql']:
                return {
                    "dbname": url.path[1:],
                    "user": url.username,
                    "password": url.password,
                    "host": url.hostname
                }
            else:
                return dict(kv.split('=') for kv in self.db_dsn.split(' '))
            
        else:
            dbname = os.environ.get('PGDATABASE', None)
            user = os.environ.get('PGUSER', None)
            password = os.environ.get('PGPASSWORD', None)
            host = os.environ.get('PGHOST', None)

            params = {}
            if dbname is not None:
                params["dbname"] = dbname
            if user is not None:
                params["user"] = user
            if password is not None:
                params["password"] = password
            if host is not None:
                params["host"] = host
            
            return params


    def get_connection(self, transactional=True):
        """
        Retrieve a database connection.  
        If self.dbname exists, then the connection returned is to the named database
        otherwise the connection is to the generic db instance
        """
        if self.db_exists():
            params = self.connection_params()
            params["dbname"] = self.dbname
            conn = psycopg2.connect(**params)
        else:
            conn = psycopg2.connect(**self.connection_params()) 

        if not transactional:
            conn.set_session(autocommit=True)
        
        return conn 


    def role_exists(self, role):
        return role in self.get_roles()

    def get_roles(self):
        """
        Fetch the roles defined in the database
        """
        conn = self.get_connection()
        with conn.cursor() as cur:
            # Fetch all roles
            cur.execute(f"SELECT rolname from pg_catalog.pg_roles")
            roles = [row[0] for row in cur.fetchall()]
        
        conn.close()
        return roles

    def get_users_roles(self, user):
        """
        Fetch the roles assigned to a user
        """
        conn = self.get_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                        SELECT r.rolname 
                        FROM pg_roles r
                        JOIN pg_auth_members m ON r.oid = m.roleid
                        JOIN pg_roles u on U.oid = m.member
                        WHERE u.rolname = '{user}'
                        """)
            roles = [row[0] for row in cur.fetchall()]
        
        conn.close()
        return roles

    def db_exists(self):
        """
        Check if database exists
        """
        # Open a cursor to perform database operations
        with  psycopg2.connect() as conn:
            with conn.cursor() as cur:
                # Test if database exists
                cur.execute(f"SELECT FROM pg_database WHERE datname = '{self.dbname}'")
                return len(cur.fetchall()) > 0

    def create_roles(self):
        """
        Create admin, readonly, and readwrite roles
        """

        current_roles = self.get_roles()

        conn = self.get_connection()
        with conn.cursor() as cur:

            print(f"Revoking public access to {self.dbname}")
            cur.execute(f"REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cur.execute(f"REVOKE ALL ON DATABASE {self.dbname} FROM PUBLIC")
            
            print(f"Creating Schema {self.schema}")
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema} ")

            # Create admin role
            if self.admin_role not in current_roles:
                print(f"Creating role {self.admin_role}")
                cur.execute(f"CREATE ROLE {self.admin_role} CREATEROLE")
                cur.execute(f"GRANT CONNECT ON DATABASE {self.dbname} to {self.admin_role}")
                cur.execute(f"GRANT USAGE, CREATE ON SCHEMA {self.schema} TO {self.admin_role}")
                cur.execute(f"GRANT ALL ON DATABASE {self.dbname} to {self.admin_role}")
                # the user issuing these commands must be a member of this admin role. Otherwise, Amazon RDS will not
                # allow the commands to be executed.
                user = conn.get_dsn_parameters()["user"]
                cur.execute(f"GRANT {self.admin_role} TO {user}")

            else:
                print(f"Role {self.admin_role} already exists")

            # Create replication role
            if self.replication_role not in current_roles:
                print(f"Creating role {self.replication_role}")
                cur.execute(f"CREATE ROLE {self.replication_role} REPLICATION LOGIN")
                cur.execute(f"GRANT CONNECT ON DATABASE {self.dbname} TO {self.replication_role}")
                cur.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {self.replication_role}")
                cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {self.schema} TO {self.replication_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT ON TABLES TO {self.replication_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT ON SEQUENCES TO {self.replication_role}")


            # Create readonly role
            if self.ro_role not in current_roles:
                print(f"Creating role {self.ro_role}")
                cur.execute(f"CREATE ROLE {self.ro_role} ADMIN {self.admin_role}")
                cur.execute(f"GRANT CONNECT ON DATABASE {self.dbname} TO {self.ro_role}")
                cur.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {self.ro_role}")
                cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {self.schema} TO {self.ro_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT ON TABLES TO {self.ro_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT ON SEQUENCES TO {self.ro_role}")
            else:
                print(f"Role {self.ro_role} already exists")

            # Create readwrite role
            if self.rw_role not in current_roles:
                print(f"Creating role {self.rw_role}")
                cur.execute(f"CREATE ROLE {self.rw_role} ADMIN {self.admin_role}")
                cur.execute(f"GRANT CONNECT ON DATABASE {self.dbname} TO {self.rw_role};")
                cur.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {self.rw_role}")
                cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {self.schema} TO {self.rw_role}")
                cur.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {self.schema} TO {self.rw_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT USAGE ON SEQUENCES TO {self.rw_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {self.rw_role}")
            else:
                print(f"Role {self.rw_role} already exists")

           
        conn.commit()
        conn.close()

    def create_user(self, username, password, role):

        current_roles = self.get_roles()

        if role not in current_roles:
            print(f"Role {role} does not exist. Please create role first")
            return

        # If the username is an existing role, then update the password
        if username in current_roles:
            self.update_password_and_role(username, password, role)
            return

        conn = self.get_connection()
        with conn.cursor() as cur:

            print(f"Creating user {username}")
            cur.execute(f"CREATE USER {username} WITH PASSWORD '{password}'")
            if role != username:
                cur.execute(f"GRANT {role} TO {username}")

        conn.commit()
        conn.close()

    def update_password_and_role(self, username, password, role):
        conn = self.get_connection()
        with conn.cursor() as cur:
            
            if role != username:
                print(f"Updating role for {username}")
                current_roles = self.get_users_roles(username)
                for r in current_roles:
                    cur.execute(f"REVOKE {r} FROM {username}")
                cur.execute(f"GRANT {role} TO {username}")

            print(f"Updating password for {username}")
            cur.execute(f"ALTER ROLE {username} WITH LOGIN PASSWORD '{password}'")

        
        conn.commit()

    def create_database(self):
        """
        Creates a new database with name dbname
        and configures admin, ro, and rw roles in the db
        """
        
        # Open a cursor to perform database operations
        conn = self.get_connection(transactional=False)
        with conn.cursor() as cur:

            if not self.db_exists():
                print(f"Creating database {self.dbname}")
                cur.execute(f"CREATE DATABASE {self.dbname}")
            else:
                print(f"Database {self.dbname} already exists.")
        
        conn.close()
        
    def rename_database(self, dbname, new_name):
        """
        Rename the database to a new name
        """
        conn = self.get_connection()
        with conn.cursor() as cur:
            print(f"Renaming database {dbname} to {new_name}")
            cur.execute(f"ALTER DATABASE {dbname} RENAME TO {new_name}")
        conn.commit()
        conn.close()

    def write_env(self):
        """
        Write the environment file for the database
        """
        filename = f".env.{self.dbname_no_env}.{self.environment}"

        conn = self.get_connection()
        dbhost = conn.get_dsn_parameters().get("host", "localhost")
        conn.close()

        def sanitize(s):
            # Replace special characters with url codes
            return s.replace('@', '%40').replace(':', '%3A')
        
        with open(filename, 'w') as file:
            file.write(f'DB_URL=postgresql://{self.admin_role}:{sanitize(self.adminpw)}@{dbhost}/{self.dbname}\n')
            if self.ropw is not None:
                file.write(f'# DB_URL=postgresql://{self.ro_role}:{sanitize(self.ropw)}@{dbhost}/{self.dbname}\n')
            if self.rwpw is not None:
                file.write(f'# DB_URL=postgresql://{self.rw_role}:{sanitize(self.rwpw)}@{dbhost}/{self.dbname}\n')
    
        print(f"Environment written to {filename}")


    def check_grants(self):
        conn = self.get_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
    SELECT r.rolname, 
           r.rolcanlogin,
        ARRAY(SELECT b.rolname
                FROM pg_catalog.pg_auth_members m
                JOIN pg_catalog.pg_roles b ON (m.roleid = b.oid)
                WHERE m.member = r.oid) as memberof,
        ARRAY(SELECT DISTINCT rtg.table_catalog
                        FROM information_schema.role_table_grants rtg
                        WHERE rtg.grantee = r.rolname) as databases
    FROM pg_catalog.pg_roles r
    WHERE r.rolname NOT IN ('pg_signal_backend','rds_iam',
                            'rds_replication','rds_superuser',
                            'rdsadmin','rdsrepladmin')
    ORDER BY 1""")
            results = cur.fetchall()
        conn.close()
        return results

def get_db_dsn(args):
    if args.db_dsn is None:
        db_dsn = os.environ.get('DB_DSN', None)
    else:
        db_dsn = args.db_dsn

    if db_dsn is None:
        print("DB_DSN must be set or specified on command line")
        exit(1)
    return db_dsn


def check_grants():
    """
    Check the grants for the database
    """
    parser = argparse.ArgumentParser(description="Check the grants for the database")
    parser.add_argument('--db-dsn', action="store", help="Database connection string")
    args = parser.parse_args()

    db_dsn = get_db_dsn(args)
    
    bootstrapper = DatabaseBootstrapper(db_dsn=db_dsn)
    results = bootstrapper.check_grants()
    for r in results:
        print(f"Role: {r[0]}")
        print(f"Can Login: {r[1]}")
        print(f"Member of: {r[2]}")
        print(f"Databases: {r[3]}")
        print()


def add_user():
    """
    Adds a new user with the specified role to the database
    """
    parser = argparse.ArgumentParser(description="Add a user to the EFN database")

    parser.add_argument('--db-dsn', action="store", help="Database connection string")
    parser.add_argument('--username', action="store", help="Username of new user")
    parser.add_argument('--password', action="store", help="Password of new user")
    parser.add_argument('--role', action="store", choices=["readonly", "readwrite", "admin"], help="Role for the user", default=None)
    
    args = parser.parse_args()

    db_dsn = get_db_dsn(args)

    bootstrapper = DatabaseBootstrapper(db_dsn=db_dsn)
    if args.role == "admin":
        role = bootstrapper.admin_role
    elif args.role == "readonly":
        role = bootstrapper.ro_role
    elif args.role == "readwrite":
        role = bootstrapper.rw_role
    else:
        print("Invalid role")
        return
        
    bootstrapper.create_user(args.username, args.password, role)


def rename_database():
    parser = argparse.ArgumentParser(description="Rename a database")

    parser.add_argument('--db-dsn', action="store", help="Database connection string")
    parser.add_argument('dbname', action="store", help="Database name")
    parser.add_argument('new_name', action="store", help="New name for the database")

    args = parser.parse_args()

    db_dsn = get_db_dsn(args)
    bootstrapper = DatabaseBootstrapper(db_dsn=db_dsn)
    bootstrapper.rename_database(args.dbname, args.new_name)


def create_database():
    parser = argparse.ArgumentParser(description="Create a database and configure roles")

    parser.add_argument('database', action="store", help="Database name")
    parser.add_argument('environment', action="store", choices=['prod', 'test', 'dev'], help="Environment name")
    parser.add_argument('--admin-password', action="store", required=True, help="admin user password")
    parser.add_argument('--ro-password', action="store", required=False, help="readonly user password")
    parser.add_argument('--rw-password', action="store", required=False, help="readwrite user password")
    
    args = parser.parse_args()
    
    bootstrapper = DatabaseBootstrapper(dbname=args.database, 
                                        environment=args.environment,
                                        adminpw=args.admin_password, 
                                        ropw=args.ro_password, 
                                        rwpw=args.rw_password)
    try:
        # Create the Database
        bootstrapper.create_database()
        
        # Configure users roles
        bootstrapper.create_roles()

        # Add users
        if args.admin_password:
            bootstrapper.create_user(bootstrapper.admin_role, args.admin_password, bootstrapper.admin_role)
        if args.ro_password:
            bootstrapper.create_user(bootstrapper.ro_role, args.ro_password, bootstrapper.ro_role)
        if args.rw_password:
            bootstrapper.create_user(bootstrapper.rw_role, args.rw_password, bootstrapper.rw_role)

        # Write the environment file
        bootstrapper.write_env()
    except psycopg2.OperationalError as e:
        print(f"Database error: {e}")
        print("Make sure that the database is running and that PGUSER, PGPASSWORD, PGDATABASE envionment variables are set")
    except Exception as e:
        print(f"Error: {e}")

def main():
    create_database()

if __name__ == "__main__":
    main()
