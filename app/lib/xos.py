import os

import requests

XOS_AUTH_TOKEN = os.environ['XOS_AUTH_TOKEN']
XOS_API_ENDPOINT = os.environ['XOS_API_ENDPOINT']

def get_or_create_xos_stub_video(video_data):
    xos_video_endpoint = f'{XOS_API_ENDPOINT}assets/'
    headers = {'Authorization': 'Token ' + XOS_AUTH_TOKEN}

    get_response = requests.get(xos_video_endpoint+'?title_contains=NOT%20UPLOADED&checksum='+video_data['master_metadata']['checksum'], headers=headers)
    get_response.raise_for_status()
    get_response_json = get_response.json()
    if get_response_json['count'] == 1:
        return get_response_json['results'][0]['id']

    response = requests.post(xos_video_endpoint, json=video_data, headers=headers)
    response.raise_for_status()
    return response.json()['id']

def update_xos_with_final_video(asset_id, video_data):
    xos_video_endpoint = f'{XOS_API_ENDPOINT}assets/{asset_id}/'
    headers = {'Authorization': 'Token ' + XOS_AUTH_TOKEN}
    response = requests.patch(xos_video_endpoint, json=video_data, headers=headers)
    response.raise_for_status()
