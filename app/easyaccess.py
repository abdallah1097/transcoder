#!/usr/bin/env python3
"""
(Watch a folder for compatible video files.)
For every compatible video file in the watch folder (assume it is a master file):
    - [x] find or create the destination folders in master and access
    - [x] if we don't have a destination access file...
    - [x] convert to access format (h264 output)
    - [x] fixity copy the files to the appropriate destination folders (leave .md5 files behind)
    - [x] move watched files to "done" folder
    - [x] ffprobe the destination files
    - [x] slack a record of what happened.
"""

import json
import logging
import tempfile
import subprocess
import os
import posixpath
import traceback
import time
from datetime import date

import settings
from lib.collection_files import (master_to_access_filename,
                                  master_to_web_filename,
                                  parse_collection_file_path)
from lib.ffmpeg import (FFMPEGError, find_video_files,
                        get_video_metadata,
                        write_metadata_summary_entry)
from lib.fixity import fixity_move, generate_file_md5, post_move_filename
from lib.formatting import seconds_to_hms
from lib.s3 import upload_to_s3
from lib.slack import post_slack_message
from lib.xos import update_xos_with_final_video, update_xos_with_stub_video

logging.basicConfig(format='%(asctime)s: %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)


def new_file_slack_message(message, file_path, duration):
    # post a link to a folder/file with an SMB mount.
    if file_path.startswith(settings.MASTER_FOLDER):
        url = file_path.replace(settings.MASTER_FOLDER, settings.MASTER_URL)
    elif file_path.startswith(settings.ACCESS_FOLDER):
        url = file_path.replace(settings.ACCESS_FOLDER, settings.ACCESS_URL)
    elif file_path.startswith(settings.WEB_FOLDER):
        url = file_path.replace(settings.WEB_FOLDER, settings.WEB_URL)
    else:
        raise ValueError("%s doesn't seem to be in either the Master, Access or Web folders. Not sure how to make a URL for this." % file_path)

    dirname = os.path.dirname(url)
    attachments = [
        {
            "fallback": "Open folder at %s" % dirname,
            "actions": [
                {
                    "type": "button",
                    "text": "View file :cinema:",
                    "url": url,
                    "style": "primary" # or danger
                },
                {
                    "type": "button",
                    "text": "Open folder :open_file_folder:",
                    "url": dirname,
                },
            ]
        }
    ]

    formatted_message = "%s: %s (Duration %s)" % (message, os.path.basename(url), duration)
    post_slack_message(formatted_message, attachments=attachments)


def post_slack_exception(message):
    traceback.print_exc()
    logging.warning(message)
    post_slack_message(message)


def convert_and_get_metadata(source_file_path, dest_file_path):
    if os.path.exists(dest_file_path):
        message = "Cancelling video conversion: " + dest_file_path + " already exists."
        logging.warning(message)
        post_slack_message(message)
        return

    with tempfile.TemporaryDirectory() as tmp_folder:
        tmp_path = os.path.join(tmp_folder, os.path.basename(dest_file_path))
        ffmpeg_args = ["ffmpeg", '-i', source_file_path] + settings.FFMPEG_ARGS + [tmp_path]
        cmd_str = " ".join(ffmpeg_args)
        logging.info("Running " + cmd_str)
        r = subprocess.run(ffmpeg_args, check=True)
        fixity_move(tmp_path, dest_file_path, failsafe_folder=None)
        logging.info("Conversion complete: " + dest_file_path)

    metadata = get_video_metadata(dest_file_path)
    with open(dest_file_path + ".json", 'w') as f:
        json.dump(metadata, f, indent=2, default=str)
    vernon_id, file_type, title = parse_collection_file_path(dest_file_path)
    metadata.update({'vernon_id': vernon_id, 'filetype': file_type, 'title': title})
    write_metadata_summary_entry(metadata)
    new_file_slack_message("*New file* :hatching_chick:", dest_file_path, seconds_to_hms(metadata['duration_secs']))

    return metadata


# The transcoder exits after the first transcode. The service continually restarts in Balena, so we need only
# process the first file. This improves the scope for parallelisation since many transcoders will each just pick
# up the first unlocked file rather than looping through all files in parallel and potentially coming into
# conflict.
def main():
    # LOOK FOR VIDEO FILES TO CONVERT
    try:
        logging.info("Looking for video files to convert...")
        logging.info("settings.WATCH_FOLDER: %s." % settings.WATCH_FOLDER)
        files = find_video_files(settings.WATCH_FOLDER)
        source_file_path = next(files)
        logging.info("source_file_path: %s" % source_file_path)
        logging.info("Looking for video files to convert... DONE\n")
    except StopIteration:
        # Service is continually started, which is a waste of time/log space if there are no new files.
        logging.info("No files found. Waiting 1hr.\n")
        time.sleep(3600)
        return


    # MAKE SURE WE HAVE THE DESTINATION FOLDERS
    try:
        logging.info("Making sure we have the destination folders...")
        master_filename = os.path.basename(source_file_path)
        access_filename = master_to_access_filename(master_filename, settings.FFMPEG_DESTINATION_EXT)
        web_filename = master_to_web_filename(master_filename, settings.FFMPEG_DESTINATION_EXT)

        vernon_id, file_type, title = parse_collection_file_path(master_filename)
        destination_master_folder = settings.MASTER_FOLDER + vernon_id + '_' + title + '/'
        destination_access_folder = settings.ACCESS_FOLDER + vernon_id + '_' + title + '/'
        destination_web_folder = settings.WEB_FOLDER + vernon_id + '_' + title + '/'

        if not os.path.exists(destination_master_folder): os.mkdir(destination_master_folder)
        if not os.path.exists(destination_access_folder): os.mkdir(destination_access_folder)
        if not os.path.exists(destination_web_folder): os.mkdir(destination_web_folder)

        master_file_path = destination_master_folder + master_filename
        access_file_path = destination_access_folder + access_filename
        web_file_path = destination_web_folder + web_filename

        logging.info("master_file_path: %s" % master_file_path)
        logging.info("access_file_path: %s" % access_file_path)
        logging.info("web_file_path: %s" % web_file_path)

        logging.info("Making sure we have the destination folders... DONE\n")
    except Exception as e:
        return post_slack_exception("Could not make sure we have the destination folders. There may be something funny with the file name: %s" % e)


    # UPDATE XOS WITH STUB VIDEO
    try:
        logging.info("Updating XOS with stub video...")
        generate_file_md5(source_file_path, store=True)
        master_metadata = get_video_metadata(source_file_path)
        asset_id = update_xos_with_stub_video({
            'title': master_filename+" NOT UPLOADED",
            'original_file_metadata': json.dumps(master_metadata, default=str)
        })
        logging.info("Stub video django ID: %s" % asset_id)
        logging.info("Updating XOS with stub video... DONE\n")
    except Exception as e:
        return post_slack_exception("Couldn't update XOS: %s" % e)


    # CONVERT TO ACCESS AND WEB FORMATS
    try:
        logging.info("Converting to access format...")
        access_metadata = convert_and_get_metadata(source_file_path, access_file_path)
        logging.info("Converting to access format... DONE\n")
        logging.info("Converting to web format...")
        web_metadata = convert_and_get_metadata(source_file_path, web_file_path)
        logging.info("Converting to web format... DONE\n")
    except Exception as e:
        return post_slack_exception("Could not convert to access and web formats: %s" % e)


    # MOVE THE SOURCE FILE INTO THE MASTER FOLDER
    try:
        logging.info("Moving the source file into the master folder...")
        fixity_move(source_file_path, master_file_path, failsafe_folder=settings.OUTPUT_FOLDER)
        with open(master_file_path + ".json", 'w') as f:
            json.dump(master_metadata, f, indent=2, default=str)
        master_metadata.update({'vernon_id': vernon_id, 'filetype': file_type, 'title': title})
        write_metadata_summary_entry(master_metadata)
        new_file_slack_message("*New master file* :movie_camera:", master_file_path, seconds_to_hms(master_metadata['duration_secs']))
        logging.info("Moving the source file into the master folder... DONE\n")
    except Exception as e:
        return post_slack_exception("Couldn't move the source file into the master folder: %s" % e)


    # UPLOAD THE ACCESS AND WEB FILES TO S3
    try:
        logging.info("Uploading access file to S3...")
        upload_to_s3(access_file_path)
        logging.info("Uploading access file to S3... DONE\n")
        logging.info("Uploading web file to S3...")
        upload_to_s3(web_file_path)
        logging.info("Uploading web file to S3... DONE\n")
    except Exception as e:
        return post_slack_exception("%s Couldn't upload to S3" % e)


    # UPDATE XOS VIDEO URLS AND METADATA
    try:
        logging.info("Updating XOS video urls and metadata...")
        generate_file_md5(master_file_path, store=True)
        update_xos_with_final_video(asset_id, {
            'title': master_filename,
            'access_file': os.path.basename(access_file_path),
            'web_file': os.path.basename(web_file_path),
            'access_metadata': json.dumps(access_metadata, default=str),
            'web_metadata': json.dumps(web_metadata, default=str)
        })
        logging.info("Updating XOS video urls and metadata... DONE\n")
    except Exception as e:
        return post_slack_exception("%s Couldn't update XOS video urls and metadata" % e)

    logging.info("=" * 80)

if __name__ == "__main__":
    main()
