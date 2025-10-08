"""
Script to drop tables from an RDS MySQL database while handling foreign key dependencies.

Usage:
    python drop_dop_tables.py --db-host=my-db-host --db-name=my-db

Arguments:
    --db-host      The RDS database host.
    --db-name      The database name.
    --dry-run      Enable dry run mode (no actual changes).

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
    python drop_dop_tables.py --db-host=mydb.amazonaws.com --db-name=mydatabase --dry-run
"""

import boto3
import click
import backoff
from botocore.exceptions import ClientError
import pymysql
import logging
from datetime import datetime, timedelta


MAX_TRIES = 5

TABLES_TO_DROP = [
    "third_party_auth_providerapipermissions",  # FK reference to oauth2_client
    "oauth2_provider_trustedclient",  # FK reference to oauth2_client
    "oauth2_grant",  # FK references to oauth2_client, auth_user
    "oauth2_accesstoken",  # FK references to oauth2_client, auth_user
    "oauth2_refreshtoken",  # FK references to oauth2_accesstoken, oauth2_client, auth_user
    "oauth_provider_token",  # FK references to oauth_provider_consumer, oauth_provider_scope, auth_user
    "oauth_provider_consumer",  # FK reference to auth_user
    "oauth2_client",  # No FK references, but referenced by multiple tables
    "oauth_provider_scope",  # Referenced by oauth_provider_token
    "oauth_provider_nonce",  # No known FK references
]
FK_DEPENDENCIES = {
    "third_party_auth_providerapipermissions": ["oauth2_client"],
    "oauth2_provider_trustedclient": ["oauth2_client"],
    "oauth2_grant": ["oauth2_client", "auth_user"],
    "oauth2_accesstoken": ["oauth2_client", "auth_user"],
    "oauth2_refreshtoken": ["oauth2_accesstoken", "oauth2_client", "auth_user"],
    "oauth_provider_token": ["oauth_provider_consumer", "oauth_provider_scope", "auth_user"],
    "oauth_provider_consumer": ["auth_user"],
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


def drop_foreign_key(connection, db_name, table_name, referenced_table, dry_run):
    query = f"""
    SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = '{table_name}' AND REFERENCED_TABLE_NAME = '{referenced_table}';
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        result = cursor.fetchone()
        if result:
            constraint_name = result["CONSTRAINT_NAME"]
            drop_query = f"ALTER TABLE {table_name} DROP FOREIGN KEY {constraint_name};"
            if dry_run:
                logging.info(f"[Dry Run] Would drop foreign key {constraint_name} from {table_name}.")
            else:
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
        if result and result["last_activity"]:
            return datetime.strptime(str(result["last_activity"]), "%Y-%m-%d %H:%M:%S")
        return None  # If no activity, return None


def check_all_tables_before_proceeding(connection):
    """ Check if any table has recent activity (within 12 months) """
    one_year_ago = datetime.now() - timedelta(days=365)

    for table in TABLES_TO_DROP:
        last_activity = get_last_activity_date(connection, table)
        if last_activity and last_activity > one_year_ago:
            logging.info(f"Skipping all operations: Table {table} has recent activity on {last_activity}.")
            return False  # Stop execution if any table is active

    logging.info("All tables have no updates in the last 12 months. Proceeding with FK and table drops.")
    return True  # Continue execution if all tables are inactive


def drop_table(connection, table_name, dry_run):
    logging.info(f"Dropping table {table_name}...")
    if dry_run:
        logging.info(f"[Dry Run] Would drop table {table_name}.")
    else:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        connection.commit()
        logging.info(f"Table {table_name} dropped.")


@click.command()
@click.option('--db-host', required=True, help="RDS DB host")
@click.option('--db-user', envvar='DB_USERNAME', required=True, help="RDS DB user (can be set via environment variable DB_USERNAME)")
@click.option('--db-password', envvar='DB_PASSWORD', required=True, help="RDS DB password (can be set via environment variable DB_PASSWORD)")
@click.option('--db-name', required=True, help="RDS DB name")
@click.option('--dry-run', is_flag=True, help="Enable dry run mode (no actual changes)")
def drop_tables(db_host, db_user, db_password, db_name, dry_run):
    """
    A script to drop tables from an RDS database while handling foreign key dependencies.
    Table names are read from the provided file.
    """
    try:
        connection = connect_to_db(db_host, db_user, db_password, db_name)

        tables_activity = check_all_tables_before_proceeding(connection)
        if tables_activity:
            for table, referenced_tables in FK_DEPENDENCIES.items():
                for referenced_table in referenced_tables:
                    drop_foreign_key(connection, db_name, table, referenced_table, dry_run)

            for table in TABLES_TO_DROP:
                drop_table(connection, table, dry_run)

            connection.close()
            logging.info("Database cleanup completed successfully.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")


if __name__ == '__main__':
    drop_tables()
