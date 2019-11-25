import os
import sys
import boto3

"""
Usage:
env `cat dev.env | xargs` python rms3.py <filename on s3>
"""

file_to_be_deleted = sys.argv[1]
print("Deleting "+file_to_be_deleted+"...")
client = boto3.client(
    's3',
    aws_access_key_id=os.environ['ACCESS_KEY'],
    aws_secret_access_key=os.environ['SECRET_KEY'],
)
response = client.delete_object(Bucket='xos-transcoding-media', Key=file_to_be_deleted)
response = client.list_objects(Bucket='xos-transcoding-media')
print("Deleted.")

# Do an ls
try:
    for x in response['Contents']:
        print(x['LastModified'].strftime("%m/%d/%Y %H:%M:%S")+" "+x['Key'])
except KeyError:
    print("Pretty sure there's nothing in this bucket.. at least not anymore")
