import json
import boto3
from botocore.exceptions import ClientError

# Make sure that any email address you plan to send to is added to SES
# Also: this assumes the name of your account IS an email address
sender_email = 'source email address'
always_send_to = ['<addresses to always send to>']


def send_email(source: str, target: str, body: str, email_client):
    targets = []
    targets.extend(always_send_to)
    if target is not None and "@" in target:
        targets.append(target)

    try:
        # Provide the contents of the email.
        response = {
            "MessageId": f"{source} - {targets}"
        }

        # response = email_client.send_email(
        #     Destination={
        #         'ToAddresses': targets
        #     },
        #     Message={
        #         'Body': {
        #             'Text': {
        #                 'Charset': "UTF-8",
        #                 'Data': body,
        #             },
        #         },
        #         'Subject': {
        #             'Charset': "UTF-8",
        #             'Data': "Your instance is still running",
        #         },
        #     },
        #     Source=source
        # )
    # Display an error if something goes wrong.
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID: {0}".format(response['MessageId'])),


def send_warning_email(source: str, target: str, instance_name: str, region: str, email_client):
    hail = "-unknown-" if target is None else target


    message = """
Hi {email},

You have left instance {instance} on in region {region}. If this is intentional that's fine, if not please
turn of your machine.

Thank you very much in advance,

Lambda-bot
    """.format(email=hail, instance=instance_name, region=region)
    send_email(source, target, message, email_client=email_client)


"""
EC2
"""


def inform_about_running_instances(instances: list, region: str):
    email_client = boto3.client('ses', region_name=region)
    local_cloudtrail = boto3.client('cloudtrail', region_name=region)

    events = local_cloudtrail.lookup_events(
        LookupAttributes=[{
            'AttributeKey': 'EventName',
            'AttributeValue': 'RunInstances'
        }],
        MaxResults=100
    )['Events']

    for instance in instances:
        inform_for_instance(instance['InstanceId'], email_client, events, region)


def inform_for_instance(instance_id: str, email_client, events: dict, region: str):
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


def check_region_ec2(region: str):
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


"""
Sagemaker
"""


def inform_about_running_notebook(notebook: dict, region: str):
    email_client = boto3.client('ses', region_name=region)
    local_cloudtrail = boto3.client('cloudtrail', region_name=region)
    notebook_name = notebook["NotebookInstanceName"]
    notebook_arn = notebook["NotebookInstanceArn"]

    events = local_cloudtrail.lookup_events(
        LookupAttributes=[{
            'AttributeKey': 'EventName',
            'AttributeValue': 'CreateNotebookInstance'
        }],
        MaxResults=100
    )['Events']

    email_send = False
    for event in events:
        raw_cloudtrail_event = json.loads(event["CloudTrailEvent"])

        try:
            event_notebook_arn = raw_cloudtrail_event["responseElements"]["notebookInstanceArn"]
            if event_notebook_arn == notebook_arn:
                email_address = event['Username']
                send_warning_email(sender_email, email_address, notebook_name, region, email_client)
                email_send = True
                break
        except KeyError:
            # We're not entirely sure if the cloudtrail event will always contain the right dictionary.
            # Don't crash if we can't find the right key
            print(f"Did not find the event's notebook ARN. Raw event: {event['CloudTrailEvent']}")
    if not email_send:
        send_warning_email(sender_email, None, notebook_name, region, email_client)


def check_region_sagemaker(region: str):
    local_ec2 = boto3.client('sagemaker', region_name=region)
    response = local_ec2.list_notebook_instances()

    notebooks = response['NotebookInstances']

    for notebook in notebooks:
        instances_state = notebook['NotebookInstanceStatus']
        if instances_state in ["Pending", "InService"]:
            inform_about_running_notebook(notebook, region)


def lambda_handler(event, context):
    global_ec2 = boto3.client('ec2', region_name="us-east-1")
    all_regions = global_ec2.describe_regions()['Regions']

    for region in all_regions:
        check_region_ec2(region['RegionName'])
        check_region_sagemaker(region['RegionName'])
