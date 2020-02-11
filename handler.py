import json
import boto3
from botocore.exceptions import ClientError

# Make sure that any email address you plan to send to is added to SES
# Also: this assumes the name of your account IS an email address
sender_email = 'source email address'
always_send_to = ['<addresses to always send to>']


def _send_email(source: str, target: str, instance_name: str, region: str, email_client):
    """
    Sends a warning email for a running instance

    :param source: Source email from which the email will be send. Required for sns.send_email
    :param target: Target email address.
    If None, the email will still be send to every user in the 'always_send_to' list
    :param instance_name: The name of the running instance
    :param region: String. The AWS region where the machine is.
    :param email_client: A boto3 ses client
    """
    body = _create_warning_email(target, instance_name, region)
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


def _create_warning_email(target: str, instance_name: str, region: str):
    """
    Formats a proper warning email about a running instance

    :param target: Target owner of the instance
    :param instance_name: The name of the instance
    :param region: String. The AWS region where the machine is.
    :return: A formatted string to be used as the email body
    """
    hail = "-unknown-" if target is None else target


    message = """
Hi {email},

You have left instance {instance} on in region {region}. If this is intentional that's fine, if not please
turn of your machine.

Thank you very much in advance,

Lambda-bot
    """.format(email=hail, instance=instance_name, region=region)
    return message


"""
EC2
"""


def _inform_about_running_instances(instances: list, region: str):
    """
    Looks for the owner of a (potentially group of) running EC2 instance(s) so we can inform them.

    Note that if the instance was started 90 days or more ago, we can't retrieve the event in CloudTrail anymore

    :param instances: A list of EC2 instances
    :param region: String. The AWS region where the machine is.
    """
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
        _inform_for_instance(instance['InstanceId'], email_client, events, region)


def _inform_for_instance(instance_id: str, email_client, events: dict, region: str):
    """
    Looks for the owner of a running notebook instance so we can inform them.

    :param instance_id: The instance id of the running instance
    :param email_client: A boto3 ses client
    :param events: CloudTrail events of the RunInstances type
    :param region: String. The AWS region where the machine is.
    """
    email_send = False
    for event in events:

        for resource in event['Resources']:
            if (resource['ResourceType'] == 'AWS::EC2::Instance' and instance_id == resource['ResourceName']):
                email_address = event['Username']
                _send_email(sender_email, email_address, instance_id, region, email_client)
                email_send = True
                break

        if email_send:
            break
    if not email_send:
        _send_email(sender_email, None, instance_id, region, email_client)


def _check_region_ec2(region: str):
    """
    Checks one region for running EC2 instances

    :param region: String. The AWS region to check.
    """
    local_ec2 = boto3.client('ec2', region_name=region)
    response = local_ec2.describe_instances(Filters=[{
        'Name': 'instance-state-code',
        'Values': ['16']  # 16: running. 80: stopped
    }])

    reservations = response['Reservations']

    for reservation in reservations:
        instances = reservation['Instances']
        if (len(instances) > 0):
            _inform_about_running_instances(instances, region)


"""
Sagemaker
"""


def _inform_about_running_notebook(notebook: dict, region: str):
    """
    Looks for the owner of a running notebook instance so we can inform them.

    Note that if the instance was started 90 days or more ago, we can't retrieve the event in CloudTrail anymore

    :param notebook: A dictionary containing at least the instance name and ARN of the notebook instance
    :param region: String. The AWS region where the machine is.
    """
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
                _send_email(sender_email, email_address, notebook_name, region, email_client)
                email_send = True
                break
        except KeyError:
            # We're not entirely sure if the cloudtrail event will always contain the right dictionary.
            # Don't crash if we can't find the right key
            print(f"Did not find the event's notebook ARN. Raw event: {event['CloudTrailEvent']}")
    if not email_send:
        _send_email(sender_email, None, notebook_name, region, email_client)


def _check_region_sagemaker(region: str):
    """
    Checks one region for running Sagemaker notebook instances

    :param region: String. The AWS region to check.
    """
    local_ec2 = boto3.client('sagemaker', region_name=region)
    response = local_ec2.list_notebook_instances()

    notebooks = response['NotebookInstances']

    for notebook in notebooks:
        instances_state = notebook['NotebookInstanceStatus']
        if instances_state in ["Pending", "InService"]:
            _inform_about_running_notebook(notebook, region)


def lambda_handler(event, context):
    global_ec2 = boto3.client('ec2', region_name="us-east-1")
    all_regions = global_ec2.describe_regions()['Regions']

    for region in all_regions:
        _check_region_ec2(region['RegionName'])
        _check_region_sagemaker(region['RegionName'])
