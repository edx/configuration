import boto3
from botocore.exceptions import ClientError
import sys
import backoff
import pymysql
import time
import uuid
import click
import re
from datadog import initialize, api


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


def rds_extractor(environment, whitelistregions):
    """
    Return list of all RDS instances across all the regions
    Returns:
        [
            {
                'name': name,
                'ARN': RDS ARN,
                'Region': Region of RDS
            }
        ]
    """
    client_region = EC2BotoWrapper()
    rds_list = []
    try:
        regions_list = client_region.describe_regions()
    except ClientError as e:
        print(f"Unable to connect to AWS with error :{e}")
        sys.exit(1)
    if whitelistregions:
        regions_list = {'Regions': [region for region in regions_list['Regions'] if region['RegionName'] in whitelistregions]}
    for region in regions_list["Regions"]:
        try:
            rds_client = RDSBotoWrapper(region_name=region["RegionName"])
            response = rds_client.describe_db_instances()
            for instance in response.get('DBInstances'):
                if environment in instance.get("Endpoint").get("Address") and "test" not in instance["DBInstanceIdentifier"]:
                    temp_dict = {}
                    temp_dict["name"] = instance["DBInstanceIdentifier"]
                    temp_dict["ARN"] = instance["DBInstanceArn"]
                    temp_dict["Region"] = region["RegionName"]
                    temp_dict["Endpoint"] = instance.get("Endpoint").get("Address")
                    temp_dict["Username"] = instance.get("MasterUsername")
                    temp_dict["Port"] = instance.get("Port")
                    rds_list.append(temp_dict)
        except ClientError as e:
            print(f"Unable to get RDS from this region error :{e}")
            sys.exit(1)
    return rds_list


def rds_controller(rds_list, username, password, hostname, dd_apikey, port, indexname, environment):
    for item in rds_list:
        rds_host_endpoint = item["Endpoint"]
        rds_port = item["Port"]
        connection = pymysql.connect(host=rds_host_endpoint, port=rds_port,
                                     user=username, password=password)
        cursor = connection.cursor()
        cursor.execute("""
                      SHOW ENGINE INNODB STATUS;
                    """)
        rds_result = cursor.fetchall()
        cursor.close()
        connection.close()
        regex = r"-{4,}\sLATEST DETECTED DEADLOCK\s-{4,}\s((.*)\s)*?-{4,}"
        global_str = ""
        for row in rds_result:
            matches = re.finditer(regex, row[2])
            for matchNum, match in enumerate(matches, start=1):
                global_str = match.group()
        expr = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        global_str = re.sub(expr, '', global_str)
        #to avoid empty dead locks
        if len(global_str) > 0:
            options = {
                'api_key': dd_apikey
            }
            initialize(**options)
            
            api.Event.create(
                    title="RDS INNODB STATUS", 
                    text=global_str,
                    tags=[f"env:{environment}", f"index:{index}", "source:INNODB-STATUS", "service:rds"]
                )

@click.command()
@click.option('--username', envvar='USERNAME', required=True)
@click.option('--password', envvar='PASSWORD', required=True)
@click.option('--environment', required=True, help='Use to identify the environment')
@click.option('--dd_api_key', envvar='DDAPIKEY', required=True)
@click.option('--indexname', required=True, help='Use to identify the DD index name')
@click.option('--rdsignore', '-i', multiple=True, help='RDS name tags to not check, can be specified multiple times')
@click.option('--whitelistregions', '-r', multiple=True, help='Regions to check, can be specified multiple times')
def main(username, password, environment, hostname, dd_apikey, indexname, rdsignore, whitelistregions):
    rds_list = rds_extractor(environment, whitelistregions)
    filtered_rds_list = list([x for x in rds_list if x['name'] not in rdsignore])
    rds_controller(filtered_rds_list, username, password, hostname, dd_apikey, indexname, environment)


if __name__ == '__main__':
    main()
