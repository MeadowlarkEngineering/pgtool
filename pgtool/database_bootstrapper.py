"""
Initialize a new suite of databases for 1859
"""
import argparse
import psycopg2

class DatabaseBootstrapper:

    def __init__(self, dbname, environment):
        """
        Initialize the bootstrapper with the database name and environment
        @param {string} dbname the name of the database
        @param {string} environment the environment to create the database in

        If the environment is 'prod', then the database name is used as is
        Otherwise, the database name is suffixed with the environment name
        """
        self.dbname_no_env = dbname
        self.dbname = f"{dbname}_{environment}"
        self.environment = environment
        self.schema = f"public"
        self.admin_role = self.dbname + "_admin"
        self.ro_role = self.dbname + "_readonly"
        self.rw_role = self.dbname + "_readwrite"
            

    def get_connection(self, transactional=True):
        """
        Retrieve a database connection.  
        If self.dbname exists, then the connection returned is to the named database
        otherwise the connection is to the generic db instance
        """
        if self.db_exists():
            conn = psycopg2.connect(dbname=self.dbname)
        else:
            conn = psycopg2.connect() 

        if not transactional:
            conn.set_session(autocommit=True)
        
        return conn 

    def add_user(self, role, username, password):
        """
        Creates a new login user for the database. 
        @param {string} role one of 'admin', 'ro', 'rw'
        @param {string} username 
        @param {string} password database user password
        """
        if role not in ['admin', 'ro', 'rw']:
            raise Exception(f"Invalid mode for user creation '{role}")

        
        conn= self.get_connection()
        with conn.cursor() as cur:
            
            if not self.role_exists(username):
                print(f"Creating user {username}")
                cur.execute(f"CREATE USER {username} WITH PASSWORD '{password}'")
            else:
                print(f"User {username} already exists")

            if role == 'admin':
                print(f"Granting all privileges on {self.dbname} to {username}")
                cur.execute(f"GRANT {self.admin_role} TO {username}")
            
            if role == 'ro':
                print(f"Granting read only privileges on {self.dbname} to {username}")
                cur.execute(f"GRANT {self.ro_role} TO {username}")

            if role == 'rw':
                print(f"Granting rw privileges on {self.dbname} to {username}")
                cur.execute(f"GRANT {self.rw_role} TO {username}")

        conn.commit()
        conn.close()

    def check_grants(self):
        conn = self.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
SELECT r.rolname, 
      ARRAY(SELECT b.rolname
            FROM pg_catalog.pg_auth_members m
            JOIN pg_catalog.pg_roles b ON (m.roleid = b.oid)
            WHERE m.member = r.oid) as memberof
FROM pg_catalog.pg_roles r
WHERE r.rolname NOT IN ('pg_signal_backend','rds_iam',
                        'rds_replication','rds_superuser',
                        'rdsadmin','rdsrepladmin')
ORDER BY 1""")
            print(cur.fetchall())
        conn.close()

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

    def create_users(self, adminpw, ropw, rwpw):

        current_roles = self.get_roles()

        conn = self.get_connection()
        with conn.cursor() as cur:

            print(f"Revoking public access to {self.dbname}")
            cur.execute(f"REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cur.execute(f"REVOKE ALL ON DATABASE {self.dbname} FROM PUBLIC")
            
            print(f"Creating Schema {self.schema}")
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema} ")

            # Create readonly role
            if self.ro_role not in current_roles:
                print(f"Creating role {self.ro_role}")
                cur.execute(f"CREATE USER {self.ro_role} WITH PASSWORD '{ropw}'")
                cur.execute(f"GRANT CONNECT ON DATABASE {self.dbname} TO {self.ro_role}")
                cur.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {self.ro_role}")
                cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {self.schema} TO {self.ro_role}")
            else:
                print(f"Role {self.ro_role} already exists")

            # Create readwrite role
            if self.rw_role not in current_roles:
                print(f"Creating role {self.rw_role}")
                cur.execute(f"CREATE USER {self.rw_role} WITH PASSWORD '{rwpw}'")
                cur.execute(f"GRANT CONNECT ON DATABASE {self.dbname} TO {self.rw_role};")
                cur.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {self.rw_role}")
                cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {self.schema} TO {self.rw_role}")
                cur.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {self.schema} TO {self.rw_role}")
            else:
                print(f"Role {self.rw_role} already exists")

            # Create admin role
            if self.admin_role not in current_roles:
                print(f"Creating role {self.admin_role}")
                cur.execute(f"CREATE USER {self.admin_role} WITH PASSWORD '{adminpw}'")
                cur.execute(f"GRANT CONNECT ON DATABASE {self.dbname} to {self.admin_role}")
                cur.execute(f"GRANT USAGE, CREATE ON SCHEMA {self.schema} TO {self.admin_role}")
                cur.execute(f"GRANT ALL ON DATABASE {self.dbname} to {self.admin_role}")
                
                # the user issuing these commands must be a member of this admin role. Otherwise, Amazon RDS will not
                # allow the commands to be executed.
                user = conn.get_dsn_parameters()["user"]
                cur.execute(f"GRANT {self.admin_role} TO {user}")

                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT USAGE ON SEQUENCES TO {self.rw_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {self.rw_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT ON TABLES TO {self.ro_role}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE {self.admin_role} GRANT SELECT ON SEQUENCES TO {self.ro_role}")
            else:
                print(f"Role {self.admin_role} already exists")
        conn.commit()
        conn.close()


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
        
    def write_env(self, adminpw):
        """
        Write the environment file for the database
        """
        filename = f".env.{self.dbname_no_env}.{self.environment}"

        conn = self.get_connection()
        dbhost = conn.get_dsn_parameters()["host"]
        conn.close()

        with open(filename, 'w') as file:
            file.write(f"DB_URL=postgresql://{self.admin_role}:{adminpw}@{dbhost}/{self.dbname}\n")
    

def main():
    parser = argparse.ArgumentParser(description="Bootstrap the EFN database")

    parser.add_argument('database', action="store", help="Database name")
    parser.add_argument('environment', action="store", choices=['prod', 'test', 'dev'], help="Environment name")
    parser.add_argument('--admin-password', action="store", required=True, help="admin user password")
    parser.add_argument('--ro-password', action="store", required=True, help="readonly user password")
    parser.add_argument('--rw-password', action="store", required=True, help="readwrite user password")
    
    args = parser.parse_args()
    
    bootstrapper = DatabaseBootstrapper(args.database, args.environment)
    # Create the Database
    bootstrapper.create_database()
    
    # Configure users roles
    bootstrapper.create_users(args.admin_password, args.ro_password, args.rw_password)
    
    # Write the environment file
    bootstrapper.write_env(args.admin_password)

if __name__ == "__main__":
    main()
