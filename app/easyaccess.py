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
import time
from datetime import date

import settings
from lib.collection_files import (get_or_create_collection_folder,
                                  master_to_access_filename,
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
        try:
            r = subprocess.run(ffmpeg_args, check=True)
        except subprocess.CalledProcessError as e:
            message = "Error running ffmpeg. " + cmd_str + " Returned " + e.returncode + ". Output: " + e.output
            logging.warning(message)
            post_slack_message(message)
            return
        fixity_move(tmp_path, dest_file_path, failsafe_folder=None)
        logging.info("Conversion complete: " + dest_file_path)

    metadata = get_video_metadata(dest_file_path)
    with open(dest_file_path + ".json", 'w') as f:
        json.dump(metadata, f, indent=2, default=str)
    vernon_id, file_type, title = parse_collection_file_path(dest_file_path)
    metadata.update({'vernon_id': vernon_id, 'filetype': file_type, 'title': title})
    write_metadata_summary_entry(metadata, settings.OUTPUT_FOLDER)
    new_file_slack_message("*New file* :hatching_chick:", dest_file_path, seconds_to_hms(metadata['duration_secs']))

    return metadata



def main():
    logging.info("Looking for video files to convert in %s. Press Ctrl+C (several times) to quit." % settings.WATCH_FOLDER)

    files = find_video_files(settings.WATCH_FOLDER)

    # The transcoder exits after the first transcode. The service continually restarts in Balena, so we need only
    # process the first file. This improves the scope for parallelisation since many transcoders will each just pick
    # up the first unlocked file rather than looping through all files in parallel and potentially coming into
    # conflict.

    try:
        source_file_path = next(files)
    except StopIteration:
        # Service is continually started, which is a waste of time/log space if there are no new files.
        logging.info("No files found. Waiting 1hr.")
        time.sleep(3600)
        return

    master_filename = os.path.basename(source_file_path)


    # UPDATE XOS WITH STUB VIDEO
    generate_file_md5(source_file_path, store=True)
    original_file_metadata = get_video_metadata(source_file_path)
    asset_id = update_xos_with_stub_video({
        'title': master_filename+" NOT UPLOADED",
        'original_file_metadata': json.dumps(original_file_metadata, default=str)
    })

    logging.info("=" * 80)
    logging.info("Processing %s:" % master_filename)


    # MAKE SURE WE HAVE THE DESTINATION FOLDERS
    try:
        destination_access_folder = get_or_create_collection_folder(master_filename, parent=settings.ACCESS_FOLDER)
        access_filename = master_to_access_filename(master_filename, extension=settings.FFMPEG_DESTINATION_EXT)
        destination_web_folder = get_or_create_collection_folder(master_filename, parent=settings.WEB_FOLDER)
        web_filename = master_to_web_filename(master_filename, extension=settings.FFMPEG_DESTINATION_EXT)
    except ValueError as e:
        # something funny with the file name.
        logging.warning("%s Leaving alone." % e)
        return


    # CONVERT TO ACCESS FORMAT
    access_file_path = post_move_filename(access_filename, destination_access_folder)
    access_metadata = convert_and_get_metadata(source_file_path, access_file_path)


    # CONVERT TO WEB FORMAT
    web_file_path = post_move_filename(web_filename, destination_web_folder)
    web_metadata = convert_and_get_metadata(source_file_path, web_file_path)


    # MOVE THE ORIGIN FILE INTO THE MASTER FOLDER
    try:
        # fixity move the master file, leaving a spare copy in DONE_FOLDER for the time being because we're paranoid.
        destination_master_folder = get_or_create_collection_folder(master_filename, parent=settings.MASTER_FOLDER)
        master_file_path = post_move_filename(source_file_path, destination_master_folder)
        fixity_move(source_file_path, master_file_path, failsafe_folder=settings.OUTPUT_FOLDER)
        master_metadata = get_video_metadata(master_file_path)
        with open(master_file_path + ".json", 'w') as f:
            json.dump(master_metadata, f, indent=2, default=str)

        vernon_id, file_type, title = parse_collection_file_path(master_file_path)
        master_metadata.update({'vernon_id': vernon_id, 'filetype': file_type, 'title': title})
        write_metadata_summary_entry(master_metadata, settings.OUTPUT_FOLDER)
        new_file_slack_message("*New master file* :movie_camera:", master_file_path, seconds_to_hms(master_metadata['duration_secs']))
    except (ValueError, IOError) as e:
        logging.warning("%s Leaving alone." % e)
        post_slack_message("Skipped moving source file :weary:: %s" % e)
        return


    # UPLOAD THE ORIGIN FILE TO S3
    try:
        upload_to_s3(master_file_path)
    except (Exception) as e:
        logging.warning("%s Couldn't upload to S3" % e)
        post_slack_message("Couldn't upload to S3 :disappointed:: %s" % e)
        return


    # UPDATE XOS WITH FINAL VIDEO
    try:
        generate_file_md5(master_file_path, store=True)
        update_xos_with_final_video(asset_id, {
            'title': master_filename,
            'resource': os.path.basename(master_file_path),
            'access_metadata': json.dumps(access_metadata, default=str),
            'web_metadata': json.dumps(web_metadata, default=str)
        })
    except (Exception) as e:
        logging.warning("%s Couldn't update XOS with final video" % e)
        post_slack_message("Couldn't update XOS with final video :disappointed:: %s" % e)
        return

    logging.info("=" * 80)

if __name__ == "__main__":
    main()
