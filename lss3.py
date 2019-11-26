import os
import boto3

"""
Usage:
env `cat dev.env | xargs` python lss3.py
"""

client = boto3.client(
    's3',
    aws_access_key_id=os.environ['S3_ACCESS_KEY'],
    aws_secret_access_key=os.environ['S3_SECRET_KEY'],
)
response = client.list_objects(Bucket='xos-transcoding-media')
try:
    for x in response['Contents']:
        print(x['LastModified'].strftime("%m/%d/%Y %H:%M:%S")+" "+x['Key'])
except KeyError:
    print("Pretty sure there's nothing in this bucket")
