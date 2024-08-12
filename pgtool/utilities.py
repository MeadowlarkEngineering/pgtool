"""
Database utilities
"""
import psycopg2

def db_exists(dbname, dsn=None):
    """
    Check if database exists
    """
    # Open a cursor to perform database operations
    with  psycopg2.connect(dsn=dsn) as conn:
        with conn.cursor() as cur:
            # Test if database exists
            cur.execute(f"SELECT FROM pg_database WHERE datname = '{dbname}'")
            return len(cur.fetchall()) > 0
        

def get_connection(dsn, transactional=True):
    """
    Retrieve a database connection.  
    If self.dbname exists, then the connection returned is to the named database
    otherwise the connection is to the generic db instance
    """
    conn = psycopg2.connect(dsn=dsn) 

    if not transactional:
        conn.set_session(autocommit=True)
    
    return conn 