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

import os
import json
import logging
import posixpath
import time
from datetime import date
from lib.formatting import seconds_to_hms
from lib.slack import post_slack_message
import settings
from lib.collection_files import get_or_create_collection_folder, master_to_access_filename, file_path_to_url, parse_collection_file_path
from lib.fixity import generate_file_md5, fixity_move, post_move_filename
from lib.ffmpeg import (get_video_metadata, find_video_files, convert_and_fixity_move,
                        FFMPEGError, is_url, write_video_metadata,
                        write_metadata_summary_entry)
from lib.s3 import upload_to_s3
from lib.xos import update_xos_with_stub_video, update_xos_with_final_video

logging.basicConfig(format='%(asctime)s: %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)


def new_file_slack_message(message, url, metadata):
    # post a link to a folder/file with an SMB mount.

    # fake a URL when a file is passed
    if not is_url(url):
        url = file_path_to_url(url)

    url_path = posixpath.dirname(url)
    filename = posixpath.basename(url)
    attachments = [
        {
            "fallback": "Open folder at %s" % url_path,
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
                    "url": url_path,
                },
            ]
        }
    ]
    duration = seconds_to_hms(metadata['duration_secs'])
    formatted_message = "%s: %s (Duration %s)" % (message, filename, duration)
    post_slack_message(formatted_message, attachments=attachments)


def json_datetime_fix(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))


def main():
    logging.info("Looking for video files to convert in %s. Press Ctrl+C (several times) to quit." % settings.WATCH_FOLDER)

    files = find_video_files(settings.WATCH_FOLDER)

    # The transcoder exits after the first transcode. The service continually restarts in Balena, so we need only
    # process the first file. This improves the scope for parallelisation since many transcoders will each just pick
    # up the first unlocked file rather than looping through all files in parallel and potentially coming into
    # conflict.

    try:
        working_master_file = next(files)
    except StopIteration:
        # Service is continually started, which is a waste of time/log space if there are no new files.
        logging.info("No files found. Waiting 1hr.")
        time.sleep(3600)
        return

    master_filename = os.path.basename(working_master_file)

    # UPDATE XOS WITH STUB VIDEO
    generate_file_md5(working_master_file, store=True)
    original_file_metadata = get_video_metadata(working_master_file)
    asset_id = update_xos_with_stub_video({
        'title': master_filename,
        'original_file_metadata': json.dumps(original_file_metadata, default=json_datetime_fix)
    })

    logging.info("=" * 80)
    logging.info("Processing %s:" % master_filename)

    # MAKE SURE WE HAVE THE DESTINATION FOLDERS
    try:
        destination_access_folder = get_or_create_collection_folder(master_filename, parent=settings.ACCESS_FOLDER)
        access_filename = master_to_access_filename(master_filename, extension=settings.FFMPEG_DESTINATION_EXT)
    except ValueError as e:
        # something funny with the file name.
        logging.warning("%s Leaving alone." % e)
        return

    # DO THE CONVERSION AND MOVE THE RESULT INTO PLACE
    try:
        # Test preconditions:
        # If there's no access file in the destination, then convert to one.
        final_access_file = post_move_filename(access_filename, destination_access_folder)
        # convert file and fixity move the result to its final destination
        convert_and_fixity_move(
            working_master_file,
            final_access_file,
            args=settings.FFMPEG_ARGS,
        )

        access_file_metadata = write_video_metadata(final_access_file)

        vernon_id, file_type, title = parse_collection_file_path(final_access_file)
        access_file_metadata.update({
            'vernon_id': vernon_id,
            'filetype': file_type,
            'title': title
        })
        write_metadata_summary_entry(access_file_metadata, settings.OUTPUT_FOLDER)
        #new_file_slack_message("*New access file* :hatching_chick:", final_access_file, access_file_metadata)
    except (IOError, FFMPEGError) as e:
        logging.warning("%s Leaving file alone." % e)
        #post_slack_message("Skipped access file :disappointed:: %s Leaving source file alone." % e)
        return # skip doing anything with the master file.

    # MOVE THE ORIGIN FILE INTO THE MASTER FOLDER
    try:
        # fixity move the master file, leaving a spare copy in DONE_FOLDER for the time being because we're paranoid.
        destination_master_folder = get_or_create_collection_folder(master_filename, parent=settings.MASTER_FOLDER)
        final_master_file = post_move_filename(working_master_file, destination_master_folder)
        fixity_move(
            working_master_file,
            final_master_file,
            failsafe_folder=settings.OUTPUT_FOLDER
        )
        master_file_metadata = write_video_metadata(final_master_file)
        vernon_id, file_type, title = parse_collection_file_path(final_master_file)
        master_file_metadata.update({
            'vernon_id': vernon_id,
            'filetype': file_type,
            'title': title
        })
        write_metadata_summary_entry(master_file_metadata, settings.OUTPUT_FOLDER)
        #new_file_slack_message("*New master file* :movie_camera:", final_master_file, master_file_metadata)
    except (ValueError, IOError) as e:
        logging.warning("%s Leaving alone." % e)
        #post_slack_message("Skipped moving source file :weary:: %s" % e)
        return

    # UPLOAD THE ORIGIN FILE TO S3
    try:
        upload_to_s3(final_master_file)
    except (Exception) as e:
        logging.warning("%s Couldn't upload to S3" % e)
        #post_slack_message("Couldn't upload to S3 :disappointed:: %s" % e)
        return

    # UPDATE XOS WITH FINAL VIDEO
    try:
        generate_file_md5(final_master_file, store=True)
        final_file_metadata = get_video_metadata(final_master_file)
        update_xos_with_final_video(asset_id, {
            'resource': os.path.basename(final_master_file),
            'transcoded_file_metadata': json.dumps(final_file_metadata, default=json_datetime_fix)
        })
    except (Exception) as e:
        logging.warning("%s Couldn't update XOS with final video" % e)
        #post_slack_message("Couldn't update XOS with final video :disappointed:: %s" % e)
        return

    logging.info("=" * 80)

if __name__ == "__main__":
    main()
