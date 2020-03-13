import os

# These paths are mounted into the docker container by docker-entrypoint.sh
WATCH_FOLDER = "/mount/watch/"
MASTER_FOLDER =  "/mount/master/"
ACCESS_FOLDER = "/mount/access/"
WEB_FOLDER = "/tmp/"
OUTPUT_FOLDER = "/mount/output/"

ACCESS_FFMPEG_DESTINATION_EXT = ".mp4"
ACCESS_FFMPEG_ARGS = [
    '-loglevel', 'panic',
    '-stats',
    '-hide_banner',
    '-pix_fmt', 'yuv420p',  # colour format compatible with quicktime
    '-c:v', 'libx264',
    '-preset', 'veryslow',
    # quality of conversion. Try veryslow if lots of time, or ultrafast for testing. Default is 'medium'.
    '-crf', '23',  # compression (implies bitrate): 23 is default, 18 is visually lossless
    '-c:a', 'aac',  # convert audio to aac
    '-n',  # don't overwrite existing files
]

WEB_FFMPEG_DESTINATION_EXT = ".mp4"
WEB_FFMPEG_ARGS = [
    '-loglevel', 'panic',
    '-stats',
    '-hide_banner',
    '-pix_fmt', 'yuv420p',  # colour format compatible with quicktime
    '-c:v', 'libx264',
    '-preset', 'veryslow',
    # quality of conversion. Try veryslow if lots of time, or ultrafast for testing. Default is 'medium'.
    '-crf', '28',  # compression (implies bitrate): 23 is default, 18 is visually lossless
    '-c:a', 'aac',  # convert audio to aac
    '-n',  # don't overwrite existing files
]



TIMEZONE = 'Australia/Victoria'

# for retries when copying files between volumes fail
MOVE_RETRIES = 5
RETRY_WAIT = 300  # five minutes

MASTER_URL = "smb:" + os.getenv('SMB_MASTER', "//fsqcollnas.corp.acmi.net.au/Preservation%20Masters/")
ACCESS_URL = "smb:" + os.getenv('SMB_ACCESS', "//fsqcollnas.corp.acmi.net.au/Access%20Copies/")
WEB_URL = "smb:" + os.getenv('SMB_WEB', "//fsqcollnas.corp.acmi.net.au/Web%20Copies/")
