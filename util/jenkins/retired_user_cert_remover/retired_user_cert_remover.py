"""
Script to delete downloadable certificates of inactive users from S3, based on RDS MySQL database entries.

Usage:
    python retired_user_cert_remover.py --db-host=my-db-host --db-name=my-db --dry-run

Arguments:
    --db-host       The RDS database host.
    --db-name       The database name.
    --dry-run       Run the script in dry-run mode (logs actions without deleting).
    --db-user       The RDS database user (also settable via DB_USER env var).
    --db-password   The RDS database password (also settable via DB_PASSWORD env var).

Environment Variables:
    DB_USER         Database username (alternative to --db-user).
    DB_PASSWORD     Database password (alternative to --db-password).

Functionality:
    - Connects to an RDS MySQL database and fetches certificates for inactive users.
    - Targets only certificates with a valid download URL and status 'downloadable'.
    - Deletes corresponding certificate files from S3 (verify and download locations).
    - Supports dry-run mode to simulate deletions for review.

Example:
    export DB_USER=admin
    export DB_PASSWORD=securepass
    python retired_user_cert_remover.py --db-host=mydb.amazonaws.com --db-name=edxapp --dry-run
"""

import boto3
from botocore.exceptions import ClientError
import pymysql
import backoff
import click
import sys
import logging

MAX_TRIES = 5
# Configure logging
LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class S3BotoWrapper:
    def __init__(self):
        self.client = boto3.client("s3")

    @backoff.on_exception(backoff.expo, ClientError, max_tries=MAX_TRIES)
    def delete_object(self, bucket, key):
        return self.client.delete_object(Bucket=bucket, Key=key)


def fetch_certificates_to_delete(db_host, db_user, db_password, db_name):
    try:
        connection = pymysql.connect(host=db_host, user=db_user, password=db_password, database=db_name)
        cursor = connection.cursor()
        logging.info("Running query on database...")
        cursor.execute("""
            SELECT 
                au.id as "LMS_USER_ID",
                gc.course_id as "COURSE_RUN_ID",
                gc.id as "CERTIFICATE_ID",
                gc.download_url as "CERTIFICATE_URL",
                gc.download_uuid as "DOWNLOAD_UUID",
                gc.verify_uuid as "VERIFY_UUID"
            FROM 
                auth_user as au
            JOIN 
                certificates_generatedcertificate as gc
            ON 
                gc.user_id = au.id
            WHERE 
                au.is_active = 0
                AND gc.download_url LIKE '%%https://%%'
                AND gc.status = 'downloadable'
            ORDER BY 
                LMS_USER_ID,
                COURSE_RUN_ID;
        """)
        result = cursor.fetchall()
        cursor.close()
        connection.close()
        return result
    except Exception as ex:
        logging.error(f"Database query failed with error: {ex}")
        sys.exit(1)


def delete_certificates_from_s3(certificates, dry_run):
    s3_client = S3BotoWrapper()
    for cert in certificates:
        verify_uuid = cert[5]       # VERIFY_UUID
        download_uuid = cert[4]     # DOWNLOAD_UUID

        verify_key = f"cert/{verify_uuid}"
        download_key = f"downloads/{download_uuid}/Certificate.pdf"
        try:
            if dry_run:
                logging.info(f"[Dry Run] Would delete {verify_key} from S3")
                logging.info(f"[Dry Run] Would delete {download_key} from S3")
            else:
                logging.info(f"Deleting {verify_key} from S3...")
                s3_client.delete_object("verify.edx.org", verify_key)
                logging.info(f"Deleting {download_key} from S3...")
                s3_client.delete_object("verify.edx.org", download_key)
        except ClientError as e:
            logging.error(f"Error deleting {verify_key} or {download_key}: {e}")


@click.command()
@click.option('--db-host', '-h', required=True, help='Database host')
@click.option('--db-user', envvar='DB_USER', required=True, help='Database user')
@click.option('--db-password', envvar='DB_PASSWORD', required=True, help='Database password')
@click.option('--db-name', '-db', required=True, help='Database name')
@click.option('--dry-run', is_flag=True, help='Run the script in dry-run mode without making any changes')
def controller(db_host, db_user, db_password, db_name, dry_run):
    certificates = fetch_certificates_to_delete(db_host, db_user, db_password, db_name)
    delete_certificates_from_s3(certificates, dry_run)


if __name__ == '__main__':
    controller()
