#!/usr/bin/env python3

import json
import logging
import http.client as httplib
import urllib.parse as urlparse
import boto3
import os
from botocore.exceptions import ClientError

FORMAT = '%(asctime)s %(name)s %(levelname)s %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger('NATSubnets')
logger.setLevel(logging.INFO)

region = os.environ['AWS_REGION']
ec2 = boto3.resource('ec2', region)
ec2_client = boto3.client('ec2', region)

def create_nat(subnetId):
    print('Creating NAT')
    buildNat = ec2_client.create_nat_gateway(SubnetId=subnetId,TagSpecifications=[{ 'ResourceType': 'natgateway', 'Tags': [{'Key': 'Name','Value': 'BHCNAT'}]}], ConnectivityType='private')
    print(buildNat)

def find_natgw(event, context):
    getprivnatsubnet = get_nat_subnets()
    natgw = ec2_client.describe_nat_gateways()
    if not natgw['NatGateways']:
        print("No NAT Gateways Exists")
        print(getprivnatsubnet)
        create_nat(getprivnatsubnet)
    else:
        print("NAT Gateway Found")
        for natdev in natgw['NatGateways']:
            natsubnet = natdev['SubnetId']
            natstatus = natdev['State']
            getprivnatsubnet = get_nat_subnets()
            if natstatus == 'Deleted':
                print("Found NAT Gateway Deleted " + natdev['NatGatewayId'] + ' on Subnet ' + natdev['SubnetId'])
            elif getprivnatsubnet == natsubnet:
                print(natstatus)
                if natstatus == 'available':
                    print('exists')
                else:
                    print(getprivnatsubnet)
                response = {
                    'StackId': event['StackId'],
                    'RequestId': event['RequestId'],
                    'LogicalResourceId': event['LogicalResourceId'],
                    "PhysicalResourceId": context.log_stream_name,
                    "Reason": "See the details in CloudWatch Log Stream: " +
                              context.log_stream_name,
                    "Data": {  'privatesubnet': getprivnatsubnet       },
                    'Status': 'SUCCESS'
                 }
    return response

def get_nat_subnets():
    logger.info("Looking up VPC Subnets for the current region")
    priv_subnet = []
    nat_subnet = []
    try:
        for vpc in ec2.vpcs.all():
            for subnet in vpc.subnets.all():
                for x in subnet.tags:
                    if x['Key'] == 'Name':
                        if 'Ext Subnet' in x['Value']:
                            nat_subnet.append([subnet.id, subnet.availability_zone])
                        elif 'Private subnet ' in x['Value']:
                            priv_subnet.append([subnet.id, subnet.availability_zone])
        for natsub in nat_subnet:
            for privsub in priv_subnet:
                if natsub[1] in privsub:
                    privnat = privsub[0]
        logger.info("Subnets of the current VPC is - %s", nat_subnet)
        return privnat
    except ClientError as exc:
        logger.error("Failed to find the Subnets - %s", exc)
        return False

def send_response(request, response, status=None, reason=None):
    """
    Custom function to send response to CF Template
    This is a hack, ideally we should be able to import cfnresponse
    But the module is only available if we are using code: Zipfile
    """
    if status is not None:
        response['Status'] = status
    if reason is not None:
        response['Reason'] = reason
    if 'ResponseURL' in request and request['ResponseURL']:
        try:
            url = urlparse.urlparse(request['ResponseURL'])
            body = json.dumps(response)
            https = httplib.HTTPSConnection(url.hostname)
            https.request('PUT', url.path + '?' + url.query, body)
        except ConnectionError as exc:
            logger.error("Failed to send the response to the provided URL - %s", exc)
    return response

def lambda_handler(event, context):
    try:
        response = find_natgw(event, context)
        return send_response(
            event,
            response
        )
    except Exception as ex:
        logger.error("Error while replacing the route - %s", ex)
        # traceback.print_exc()
