import json
import boto3
from botocore.exceptions import ClientError

sender_email = 'instancebot@outlook.com'
always_send_to = ['lbootsman@mobiquityinc.com']


def send_email(source, target, body, email_client):
    targets = []
    targets.extend(always_send_to)
    if target is not None:
        targets.append(target)

    try:
        # Provide the contents of the email.
        response = email_client.send_email(
            Destination={
                'ToAddresses': targets
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': "UTF-8",
                        'Data': body,
                    },
                },
                'Subject': {
                    'Charset': "UTF-8",
                    'Data': "Your instance is still running",
                },
            },
            Source=source
        )
    # Display an error if something goes wrong.
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID: {0}".format(response['MessageId'])),


def send_warning_email(source, target, instance_name, region, email_client):
    hail = "-unknown-" if target is None else target


    message = """
Hi {email},

You have left instance {instance} on in region {region}. If this is intentional that's fine, if not please
turn of your machine.

Thank you very much in advance,

Lambda-bot
    """.format(email=hail, instance=instance_name, region=region)
    send_email(source, target, message, email_client=email_client)


def inform_about_running_instances(instances, region):
    email_client = boto3.client('ses', region_name=region)
    local_cloudtrail = boto3.client('cloudtrail', region_name=region)

    response = local_cloudtrail.lookup_events(
        LookupAttributes=[{
            'AttributeKey': 'EventName',
            'AttributeValue': 'RunInstances'
        }],
        MaxResults=100
    )

    events = response['Events']
    for instance in instances:
        instance_id = instance['InstanceId']
        email_send = False

        for event in events:

            for resource in event['Resources']:
                if (resource['ResourceType'] == 'AWS::EC2::Instance' and instance_id == resource['ResourceName']):
                    email_address = event['Username']
                    send_warning_email(sender_email, email_address, instance_id, region, email_client)
                    email_send = True
                    break

            if email_send:
                break

        if not email_send:
            send_warning_email(sender_email, None, instance_id, region, email_client)


def check_region(region):
    local_ec2 = boto3.client('ec2', region_name=region)
    response = local_ec2.describe_instances(Filters=[{
        'Name': 'instance-state-code',
        'Values': ['16']  # 16: running. 80: stopped
    }])

    reservations = response['Reservations']

    for reservation in reservations:
        instances = reservation['Instances']
        if (len(instances) > 0):
            inform_about_running_instances(instances, region)


def lambda_handler(event, context):
    global_ec2 = boto3.client('ec2', region_name="us-east-1")
    all_regions = global_ec2.describe_regions()['Regions']

    for region in all_regions:
        check_region(region['RegionName'])
