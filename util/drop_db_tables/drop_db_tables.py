"""
Script to drop tables from an RDS MySQL database while handling foreign key dependencies.

Usage:
    python script.py --db-host=my-db-host --db-name=my-db

Arguments:
    --db-host      The RDS database host.
    --db-name      The database name.

Environment Variables:
    DB_USERNAME    The RDS database username (set via environment variable).
    DB_PASSWORD    The RDS database password (set via environment variable).

Functionality:
    - Drops specific tables only if they have had no activity in the last 12 months.
    - Handles foreign key constraints before dropping dependent tables.
    - Ensures safe execution using retries for AWS service interactions.

Example:
    export DB_USERNAME=admin
    export DB_PASSWORD=securepass
    python script.py --db-host=mydb.amazonaws.com --db-name=mydatabase
"""

import boto3
import click
import backoff
from botocore.exceptions import ClientError
import pymysql
import logging

MAX_TRIES = 5

TABLES_TO_DROP = [
    "oauth2_provider_trustedclient",  # FK reference to oauth2_client
    "third_party_auth_providerapipermissions",  # FK reference to oauth2_client
    "oauth2_client",
    "oauth2_grant",
    "oauth2_accesstoken",
    "oauth2_refreshtoken",
    "oauth_provider_consumer",
    "oauth_provider_nonce",
    "oauth_provider_scope",
    "oauth_provider_token",
]
FK_DEPENDENCIES = {
    "third_party_auth_providerapipermissions": "oauth2_client",
    "oauth2_provider_trustedclient": "oauth2_client",
}

# Configure logging
LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



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
    logging.info("Connecting to the database...")
    return pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )


def drop_foreign_key(connection, table_name, referenced_table):
    """ Drop the foreign key constraint only for specific tables """
    last_activity = get_last_activity_date(connection, table_name)
    if last_activity:
        one_year_ago = datetime.now() - timedelta(days=365)
        if last_activity > one_year_ago:
            logging.info(f"Skipping {table_name}: Last activity was on {last_activity}")
            return
    query = f"""
    SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE TABLE_NAME = '{table_name}' AND REFERENCED_TABLE_NAME = '{referenced_table}';
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        result = cursor.fetchone()
        if result:
            constraint_name = result["CONSTRAINT_NAME"]
            drop_query = f"ALTER TABLE {table_name} DROP FOREIGN KEY {constraint_name};"
            cursor.execute(drop_query)
            connection.commit()
            logging.info(f"Dropped foreign key {constraint_name} from {table_name}.")


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
    last_activity = get_last_activity_date(connection, table_name)
    if last_activity:
        one_year_ago = datetime.now() - timedelta(days=365)
        if last_activity > one_year_ago:
            logging.info(f"Skipping {table_name}: Last activity was on {last_activity}")
            return
    logging.info(f"Dropping table {table_name}...")
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    connection.commit()
    logging.info(f"Table {table_name} dropped.")


@click.command()
@click.option('--db-host', required=True, help="RDS DB host")
@click.option('--db-user', envvar='DB_USERNAME', required=True, help="RDS DB user (can be set via environment variable DB_USERNAME)")
@click.option('--db-password', envvar='DB_PASSWORD', required=True, help="RDS DB password (can be set via environment variable DB_PASSWORD)")
@click.option('--db-name', required=True, help="RDS DB name")
def drop_tables(db_host, db_user, db_password, db_name, table_file):
    """
    A script to drop tables from an RDS database while handling foreign key dependencies.
    Table names are read from the provided file.
    """
    try:
        tables_to_drop = read_tables_from_file(table_file)
        
        connection = connect_to_db(db_host, db_user, db_password, db_name)
        
        for table, referenced_table in FK_DEPENDENCIES.items():
            drop_foreign_key(connection, table, referenced_table)
        
        for table in TABLES_TO_DROP:
            drop_table(connection, table)
        connection.close()
        logging.info("Database cleanup completed successfully.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")


if __name__ == '__main__':
    drop_tables()
