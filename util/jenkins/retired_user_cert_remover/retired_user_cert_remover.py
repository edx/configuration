"""
Script to delete downloadable certificates of inactive users from S3 by calling
the LMS retire_certs_s3 API endpoint.

This script no longer connects directly to RDS. All certificate discovery, S3
deletion, and database updates are handled by the LMS API endpoint:
    POST /api/certificates/v1/retire_certs_s3

The LMS endpoint requires an OAuth token obtained by exchanging client_id /
client_secret (stored in AWS Secrets Manager) for a bearer token.

Usage:
    python retired_user_cert_remover.py \
        --lms-host=https://lms.example.com \
        --client-id=<DOT client id> \
        --client-secret=<DOT client secret> \
        [--dry-run]

Environment Variables:
    LMS_CLIENT_ID       OAuth client id (alternative to --client-id).
    LMS_CLIENT_SECRET   OAuth client secret (alternative to --client-secret).

Dry-run:
    Passes ?dry_run=true to the API. The LMS logs what would be deleted without
    making any changes to S3 or the database.
"""

import logging
import sys

import backoff
import click
import requests

MAX_TOKEN_ATTEMPTS = 3

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)


def get_oauth_token(lms_host, client_id, client_secret):
    """
    Exchange client credentials for a bearer token via LMS DOT.

    Returns the access token string, or exits on failure.
    """
    token_url = f'{lms_host.rstrip("/")}/oauth2/access_token/'

    @backoff.on_exception(backoff.expo, requests.RequestException, max_tries=MAX_TOKEN_ATTEMPTS)
    def _request():
        response = requests.post(
            token_url,
            data={
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()['access_token']

    try:
        token = _request()
        LOGGER.info('Successfully obtained OAuth token from %s', token_url)
        return token
    except Exception as exc:
        LOGGER.error('Failed to obtain OAuth token: %s', exc)
        sys.exit(1)


def call_retire_certs_api(lms_host, token, dry_run):
    """
    Call POST /api/certificates/v1/retire_certs_s3 on the LMS.

    Returns the parsed JSON response body.
    Exits with code 1 if the call fails entirely (non-2xx after retries).
    Exits with code 2 if the call returns 207 (partial failure).
    """
    url = f'{lms_host.rstrip("/")}/api/certificates/v1/retire_certs_s3'
    params = {'dry_run': 'true'} if dry_run else {}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    LOGGER.info('Calling %s (dry_run=%s)', url, dry_run)
    try:
        response = requests.post(url, params=params, headers=headers, timeout=600)
    except requests.RequestException as exc:
        LOGGER.error('HTTP request to retire_certs_s3 failed: %s', exc)
        sys.exit(1)

    body = {}
    try:
        body = response.json()
    except ValueError:
        pass

    if response.status_code == 200:
        LOGGER.info('retire_certs_s3 completed successfully: %s', body)
        return body

    if response.status_code == 207:
        LOGGER.warning(
            'retire_certs_s3 completed with partial failures: processed=%s failed=%s',
            body.get('processed'), body.get('failed'),
        )
        sys.exit(2)

    LOGGER.error(
        'retire_certs_s3 returned unexpected status %s: %s',
        response.status_code, body,
    )
    sys.exit(1)


@click.command()
@click.option('--lms-host', required=True, help='Base URL of the LMS (e.g. https://lms.edx.org)')
@click.option('--client-id', envvar='LMS_CLIENT_ID', required=True, help='OAuth DOT client id')
@click.option('--client-secret', envvar='LMS_CLIENT_SECRET', required=True, help='OAuth DOT client secret')
@click.option('--dry-run', is_flag=True, help='Run in dry-run mode without making any changes')
def controller(lms_host, client_id, client_secret, dry_run):
    token = get_oauth_token(lms_host, client_id, client_secret)
    call_retire_certs_api(lms_host, token, dry_run)


if __name__ == '__main__':
    controller()
