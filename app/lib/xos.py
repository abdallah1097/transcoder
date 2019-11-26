import os
import requests

XOS_AUTH_TOKEN = os.environ['XOS_AUTH_TOKEN']
XOS_API_ENDPOINT = os.environ['XOS_API_ENDPOINT']

def update_xos_with_stub_video(video_data):
    xos_video_endpoint = f'{XOS_API_ENDPOINT}assets/'
    headers = {'Authorization': 'Token ' + XOS_AUTH_TOKEN}
    response = requests.post(xos_video_endpoint, json=video_data, headers=headers)
    print(response.status_code, response)
