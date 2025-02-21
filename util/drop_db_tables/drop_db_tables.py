import boto3
import click
import backoff
from botocore.exceptions import ClientError
import pymysql

MAX_TRIES = 5


class EC2BotoWrapper:
    def __init__(self):
        self.client = boto3.client("ec2")

    @backoff.on_exception(backoff.expo, ClientError, max_tries=MAX_TRIES)
    def describe_regions(self):
        return self.client.describe_regions()


class RDSBotoWrapper:
    def __init__(self, **kwargs):
        self.client = boto3.client("rds", **kwargs)

    @backoff.on_exception(backoff.expo, ClientError, max_tries=MAX_TRIES)
    def describe_db_instances(self):
        return self.client.describe_db_instances()


def connect_to_db(db_host, db_user, db_password, db_name):
    """ Establish a connection to the RDS MySQL database """
    return pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )


def get_foreign_key_dependencies(connection, table_name):
    """ Retrieve foreign key dependencies for a given table """
    query = f"""
    SELECT 
        TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME 
    FROM 
        INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE 
        REFERENCED_TABLE_NAME IS NOT NULL
        AND (TABLE_NAME = '{table_name}' OR REFERENCED_TABLE_NAME = '{table_name}')
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def get_last_activity_date(connection, table_name):
    """ Retrieve the last activity date for a table """
    query = f"""
    SELECT MAX(GREATEST(
        COALESCE(UPDATE_TIME, '1970-01-01 00:00:00'),
        COALESCE(CREATE_TIME, '1970-01-01 00:00:00')
    )) AS last_activity 
    FROM information_schema.tables 
    WHERE TABLE_NAME = '{table_name}';
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        result = cursor.fetchone()
        return result["last_activity"] if result else None


def drop_table(connection, table_name):
    """ Drops a table after checking dependencies and last activity date """
    dependencies = get_foreign_key_dependencies(connection, table_name)
    if dependencies:
        print(f"Table {table_name} has foreign key dependencies. Skipping removal.")
        for dep in dependencies:
            print(f"Dependent on table: {dep['REFERENCED_TABLE_NAME']}")
        return
    
    last_activity = get_last_activity_date(connection, table_name)
    if last_activity:
        from datetime import datetime, timedelta
        one_year_ago = datetime.now() - timedelta(days=365)
        if last_activity > one_year_ago:
            print(f"Skipping {table_name}: Last activity was on {last_activity}")
            return
    
    print(f"Dropping table {table_name}...")
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    connection.commit()
    print(f"Table {table_name} dropped.")


def read_tables_from_file(file_path):
    """ Read table names from a given file """
    with open(file_path, "r") as file:
        return [line.strip() for line in file if line.strip()]


@click.command()
@click.option('--db-host', required=True, help="RDS DB host")
@click.option('--db-user', required=True, help="RDS DB user")
@click.option('--db-password', required=True, help="RDS DB password")
@click.option('--db-name', required=True, help="RDS DB name")
@click.option('--table-file', required=True, type=click.Path(exists=True), help="Path to the file containing table names")
def drop_tables(db_host, db_user, db_password, db_name, table_file):
    """
    A script to drop tables from an RDS database while handling foreign key dependencies.
    Table names are read from the provided file.
    """
    tables_to_drop = read_tables_from_file(table_file)
    
    connection = connect_to_db(db_host, db_user, db_password, db_name)
    
    for table in tables_to_drop:
        drop_table(connection, table)
    
    connection.close()


if __name__ == '__main__':
    drop_tables()
