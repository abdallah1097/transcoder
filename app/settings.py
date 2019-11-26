import os

# These paths are mounted into the docker container by docker-entrypoint.sh
WATCH_FOLDER = os.getenv("WATCH_FOLDER", "/mount/watch")
MASTER_FOLDER = os.getenv("MASTER_FOLDER", "/mount/master")
ACCESS_FOLDER = os.getenv("ACCESS_FOLDER", "/mount/access")
OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", "/mount/output")

FFMPEG_DESTINATION_EXT = ".mp4"
FFMPEG_ARGS = [
    '-loglevel', 'panic',
    '-stats',
    '-hide_banner',
    '-pix_fmt', 'yuv420p',  # colour format compatible with quicktime
    '-c:v', 'libx264',
    '-preset', 'medium',
    # quality of conversion. Try veryslow if lots of time, or ultrafast for testing. Default is 'medium'.
    '-crf', '23',  # compression (implies bitrate): 23 is default, 18 is visually lossless
    '-c:a', 'aac',  # convert audio to aac
    '-n',  # don't overwrite existing files
]

TIMEZONE = 'Australia/Victoria'

# for retries when copying files between volumes fail
MOVE_RETRIES = 5
RETRY_WAIT = 300  # five minutes

MASTER_URL = "smb://fsqcollnas.corp.acmi.net.au/Preservation%20Masters/"
ACCESS_URL = "smb://fsqcollnas.corp.acmi.net.au/Access%20Copies/"
