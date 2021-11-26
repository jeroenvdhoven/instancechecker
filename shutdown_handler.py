import json

import boto3

dynamo_db = "shutdown-table"
dynamo_client = boto3.client('dynamodb', region_name="eu-west-1")


def _shutdown_ec2(item: dict):
    ec2_client = boto3.client('ec2', region_name=item["region"])
    ec2_client.stop_instances(
        InstanceIds=[item["instance"]]
    )
    print("Stopped instance!")


def _shutdown_sagemaker(item: dict):
    ec2_client = boto3.client('sagemaker', region_name=item["region"])
    ec2_client.stop_notebook_instances(
        NotebookInstanceName=item["instance"]
    )
    print("Stopped notebook instance!")


def lambda_handler(event, context):
    params = event["queryStringParameters"]
    assert "request_id" in params, "No request ID present"

    request_id = params["request_id"]

    result = dynamo_client.query(
        TableName=dynamo_db,
        Select='ALL_ATTRIBUTES',
        KeyConditionExpression="request_id = :request_id",
        ExpressionAttributeValues={
            ":request_id": {"S": request_id}
        }
    )
    print(json.dumps(result))
    item = result["Items"][0]
    parsed_item = {
        k: v["S"]
        for k, v in item.items()
    }
    print("Got item:", json.dumps(parsed_item))

    for expected in ["request_id", "region", "type", "instance"]:
        assert expected in parsed_item, f"{expected} not in parsed_item"

    if parsed_item["type"] == "ec2":
        _shutdown_ec2(parsed_item)
    elif parsed_item["type"] == "sagemaker":
        _shutdown_sagemaker(parsed_item)
    else:
        raise ValueError("Your type is not supported")

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html"
        },
        "body": f"""
<html>
    <head>
        <title>Your instance has been shut down</title>
    </head>
    <body>
        <p>Congrats, your machine `{parsed_item["instance"]}` has been turned off</p>
    </body>
</html>
"""
    }
