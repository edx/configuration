"""
Script to delete downloadable certificates of inactive users from S3 by calling
the LMS retire_certs_s3 API endpoint.

This script no longer connects directly to RDS. All certificate discovery, S3
deletion, and database updates are handled by the LMS API endpoint:
    POST /api/certificates/v1/retire_certs_s3

Authentication flow:
    1. Exchange client_id / client_secret (stored in AWS Secrets Manager) for a
       JWT by POSTing to /oauth2/access_token/ with token_type=jwt.
    2. Pass the JWT in the Authorization header as:
           Authorization: JWT <token>
    The LMS uses JwtAuthentication, which requires the JWT prefix (not Bearer).

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
MAX_API_ATTEMPTS = 3

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)


def get_jwt_token(lms_host, client_id, client_secret):
    """
    Exchange client credentials for a JWT via LMS DOT.

    Requests token_type=jwt so that the LMS returns a JWT token accepted by
    JwtAuthentication (which requires Authorization: JWT <token>).

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
                'token_type': 'jwt',
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()['access_token']

    try:
        token = _request()
        LOGGER.info('Successfully obtained JWT token from %s', token_url)
        return token
    except Exception as exc:
        LOGGER.error('Failed to obtain JWT token: %s', exc)
        sys.exit(1)


def call_retire_certs_api(lms_host, token, dry_run):
    """
    Call POST /api/certificates/v1/retire_certs_s3 on the LMS.

    Returns the parsed JSON response body.
    Retries up to MAX_API_ATTEMPTS times on transient network errors.
    Exits with code 1 if the call fails entirely after retries.
    Exits with code 2 if the call returns 207 (partial failure).
    """
    url = f'{lms_host.rstrip("/")}/api/certificates/v1/retire_certs_s3'
    params = {'dry_run': 'true'} if dry_run else {}
    headers = {'Authorization': f'JWT {token}', 'Content-Type': 'application/json'}

    @backoff.on_exception(backoff.expo, requests.RequestException, max_tries=MAX_API_ATTEMPTS)
    def _request():
        response = requests.post(url, params=params, headers=headers, timeout=600)
        # Retry on 5xx server errors; 2xx/207/4xx are handled below.
        if response.status_code >= 500:
            response.raise_for_status()
        return response

    LOGGER.info('Calling %s (dry_run=%s)', url, dry_run)
    try:
        response = _request()
    except requests.RequestException as exc:
        LOGGER.error('HTTP request to retire_certs_s3 failed after retries: %s', exc)
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
    jwt_token = get_jwt_token(lms_host, client_id, client_secret)
    call_retire_certs_api(lms_host, jwt_token, dry_run)


if __name__ == '__main__':
    controller()
