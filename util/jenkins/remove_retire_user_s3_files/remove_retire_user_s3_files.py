import boto3
from botocore.exceptions import ClientError
import pymysql
import backoff
import click
import sys

MAX_TRIES = 5

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
        cursor.execute("""
            SELECT 
                gc.verify_uuid AS VERIFY_UUID, 
                gc.download_uuid AS DOWNLOAD_UUID 
            FROM 
                prod.lms_pii.auth_user AS au
            JOIN 
                prod.lms_pii.certificates_generatedcertificate AS gc
            ON 
                gc.user_id = au.id
            WHERE 
                au.is_retired = TRUE
                AND gc.download_url LIKE '%%https://%%'
                AND gc.status = 'downloadable'
            ORDER BY 
                au.id, gc.course_id;
        """)
        result = cursor.fetchall()
        cursor.close()
        connection.close()
        return result
    except Exception as ex:
        print(f"Database query failed with error: {ex}")
        sys.exit(1)


def delete_certificates_from_s3(certificates):
    s3_client = S3BotoWrapper()
    for cert in certificates:
        verify_key = f"cert/{cert[0]}"
        download_key = f"downloads/{cert[1]}/Certificate.pdf"
        try:
            print(f"Deleting {verify_key} from S3...")
            s3_client.delete_object("verify.edx.org", verify_key)
            print(f"Deleting {download_key} from S3...")
            s3_client.delete_object("verify.edx.org", download_key)
        except ClientError as e:
            print(f"Error deleting {verify_key} or {download_key}: {e}")


@click.command()
@click.option('--db-host', envvar='DB_HOST', required=True, help='Database host')
@click.option('--db-user', envvar='DB_USER', required=True, help='Database user')
@click.option('--db-password', envvar='DB_PASSWORD', required=True, help='Database password')
@click.option('--db-name', envvar='DB_NAME', required=True, help='Database name')
def controller(db_host, db_user, db_password, db_name):
    certificates = fetch_certificates_to_delete(db_host, db_user, db_password, db_name)
    delete_certificates_from_s3(certificates)


if __name__ == '__main__':
    controller()
