import csv
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from shutil import which
from urllib.parse import urlparse

import requests
from dateutil.parser import parse as parse_date
from pytz import timezone

import settings
from lib.fixity import fixity_move
from lib.formatting import seconds_to_hms

try:
    ffmpeg_location = getattr(settings, "FFMPEG_LOCATION", which("ffmpeg"))
    ffprobe_location = getattr(settings, "FFPROBE_LOCATION", which("ffprobe"))
    assert ffmpeg_location
    assert ffprobe_location

except AssertionError:
    raise EnvironmentError(
        """`ffmpeg` and `ffprobe` must be installed and available before the ffmpeg module can be imported.
        You can specify their locations using FFMPEG_LOCATION and FFPROBE_LOCATION in settings."""
    )

timezone = timezone(settings.TIMEZONE)


VIDEO_MIME_TYPES = {
    '.flv': 'video/x-flv',
    '.mp4': 'video/mp4',
    '.ts': 'video/MP2T',
    '.3gp': 'video/3gpp',
    '.mov': 'video/quicktime',
    '.avi': 'video/x-msvideo',
    '.wmv': 'video/x-ms-wmv',
    '.mpg': 'video/mpeg',
    '.mpeg': 'video/mpeg',
}

METADATA_CSV_HEADERS = [
    'vernon_id',
    'title',
    'filetype',
    'duration_secs',
    'duration_hms',
    'checksum',
    'mime_type',
    'creation_datetime',
    'file_size_bytes',
    'overall_bit_rate',
    'video_codec',
    'video_bit_rate',
    'video_max_bit_rate',
    'video_frame_rate',
    'width',
    'height',
    'audio_codec',
    'audio_channels',
    'audio_sample_rate',
    'audio_bit_rate',
    'audio_max_bit_rate',
]


class FFMPEGError(subprocess.CalledProcessError):
    def __str__(self):
        return "Command '%s' didn't complete successfully (exit status %d). Perhaps not a valid video file?" % (" ".join(self.cmd), self.returncode)


def is_url(url):
    return urlparse(url).scheme != ""


def get_file_metadata(file_location):
    if is_url(file_location):
        headers = requests.head(file_location, allow_redirects=True).headers
    else:
        headers = None

    if headers:
        modified_datetime = parse_date(headers['Last-Modified'])
        creation_datetime = modified_datetime # can't get this info over HTTP
        file_size = int(headers['content-length'])
    else:
        creation_datetime = datetime.fromtimestamp(os.path.getctime(file_location))
        modified_datetime = datetime.fromtimestamp(os.path.getmtime(file_location))
        file_size = os.path.getsize(file_location)

    return {
        'creation_datetime': timezone.localize(creation_datetime),
        'modified_datetime': timezone.localize(modified_datetime),
        'file_size_bytes': file_size,
    }


def get_video_metadata(video_location):
    """
    Use ffprobe to discern information about the video.

    :param video_location: URL or Path to video file. URLs that 30x redirect to a file are OK.
    :return: Dictionary of attributes.
    """


    ffprobe_args = [ffprobe_location, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_location]
    try:
        command = " ".join(ffprobe_args)
        logging.info("Running %s" % command)
        cmd = subprocess.run(ffprobe_args, stdout=subprocess.PIPE, check=True)
        out = cmd.stdout
        m = json.loads(out.decode('utf-8'))
    except subprocess.CalledProcessError as e:
        raise FFMPEGError(e.returncode, ffprobe_args) from e

    # put the first stream of each type in the top-level, for straightforward property access via e.g. j['video']['width']
    for stream in m['streams']:
        if stream['codec_type'] not in m:
            m[stream['codec_type']] = stream

    m_video = m.get('video', {})
    m_audio = m.get('audio', {})

    frame_rate = m_video.get('avg_frame_rate', "0/1").split("/")
    video_frame_rate = int(frame_rate[0]) * 1.0 / int(frame_rate[1])

    # TODO: these are naive datetimes at the moment. Need to make them aware.
    # Use various techniques to get the creation date. If it's in the video metadata, use that, else use the
    # file/header.

    file_metadata = get_file_metadata(video_location)
    try:
        creation_datetime = parse_date(m['format']['tags'].get('creation_time'))
    except (KeyError, ValueError, TypeError):
        creation_datetime = file_metadata['creation_datetime']

    _, ext = os.path.splitext(video_location)

    with open('%s.md5' % video_location) as checksum_file:
        checksum = checksum_file.read()

    duration_hms = seconds_to_hms(
        float(m['format'].get('duration', 0.0)),
        always_include_hours=True,
        output_frames=True,
        framerate=video_frame_rate
    )

    return {
        'mime_type': VIDEO_MIME_TYPES.get(ext, None),
        'creation_datetime': creation_datetime,
        'file_size_bytes': file_metadata['file_size_bytes'],

        'duration_secs': float(m['format'].get('duration', 0.0)),
        'duration_hms': duration_hms,
        'overall_bit_rate': int(m['format'].get('bit_rate', 0)) or None,

        'video_codec': m_video.get('codec_name', None),
        'video_bit_rate':int(m_video.get('bit_rate', 0)) or None,
        'video_max_bit_rate':int(m_video.get('max_bit_rate', 0)) or None,
        'video_frame_rate': video_frame_rate,

        'width': m_video.get('width', None), # int already
        'height': m_video.get('height', None), # int already

        'audio_codec': m_audio.get('codec_name', None),
        'audio_channels': m_audio.get('channels', None), # int
        'audio_sample_rate': int(m_audio.get('sample_rate', 0)) or None,
        'audio_bit_rate': int(m_audio.get('bit_rate', 0)) or None,
        'audio_max_bit_rate': int(m_audio.get('max_bit_rate', 0)) or None,
        'checksum': checksum,
    }

def write_video_metadata(video_location):
    """
    Call 'get_video_metadata' and write the results to an adjacent .json file'.
    :param video_location:
    :return:
    """
    metadata = get_video_metadata(video_location)
    json_path = "%s.json" % video_location
    with open(json_path, 'w') as outfile:
        json.dump(metadata, outfile, indent=2, default=str)
    return metadata


# Mini lib for network-concurrency-friendly locking/unlocking a file by writing adjacent '.lock' files.

def _lockfile(filepath):
    return "%s.lock" % filepath

def is_locked(filepath):
    return os.path.exists(_lockfile(filepath))

def lock(filepath):
    Path(_lockfile(filepath)).touch()

def unlock(filepath):
    os.remove(_lockfile(filepath))

def find_video_files(source_folder, lock_files=True):
    # generate all the video paths in the source folder
    source_folder = os.path.abspath(os.path.expanduser(source_folder))
    for dirpath, dirnames, filenames in os.walk(source_folder, followlinks=True):
        for file in filenames:
            if os.path.splitext(file)[-1] in list(VIDEO_MIME_TYPES.keys()):
                filepath = os.path.join(dirpath, file)
                # make sure the file still exists, in case another thread is running and deleted it
                if not os.path.exists(filepath):
                    continue
                if lock_files:
                    if not is_locked(filepath):
                        lock(filepath)
                        yield filepath
                        unlock(filepath)
                else:
                    yield filepath


def convert(source_path, destination_path, args=[]):
    ffmpeg_args = [
        ffmpeg_location,
        '-i', source_path] + \
        args + [
        destination_path
    ]
    logging.info("Running %s" % " ".join(ffmpeg_args))
    try:
        r = subprocess.run(ffmpeg_args, check=True)
    except subprocess.CalledProcessError as e:
        raise FFMPEGError(e.returncode, ffmpeg_args) from e

    # delete an output file if it is zero bytes
    if os.path.exists(destination_path) and os.path.getsize(destination_path) == 0:
        os.remove(destination_path)

    logging.info("Conversion complete.")


def convert_and_fixity_move(source_path, destination_path, args=[]):
    """
    Convert a file to a temp folder. On success, fixity move the result into its final folder.
    """
    if os.path.exists(destination_path):
        raise IOError("Cannot convert video: Destination %s already exists." % destination_path)

    # make a tmp folder to store the convert output (in case the output file has the same name as the input file)
    with tempfile.TemporaryDirectory() as tmp_folder:
        tmp_path = os.path.join(tmp_folder, os.path.basename(destination_path))
        convert(
            source_path,
            tmp_path,
            args,
        )

        # fixity move the result
        fixity_move(
            tmp_path, destination_path,
            failsafe_folder=None
        )

    # tmp folder is deleted at this point


def write_metadata_summary(metadata_summary, folder):
    """
    Write a summary csv file with the metadata collected from every processed video
    :param metadata_summary: list of metadata dictionaries
    :param folder: the folder where the csv file will be saved
    :return: None
    """
    if metadata_summary:
        metadata_file_path = os.path.join(folder, '%s_metadata.csv' % datetime.today().strftime("%Y%m%d"))
        metadata_file_exists = os.path.isfile(metadata_file_path)
        with open(metadata_file_path, 'a') as metadata_csv:
            metadata_csv_writer = csv.DictWriter(metadata_csv, fieldnames=METADATA_CSV_HEADERS)
            if not metadata_file_exists:
                metadata_csv_writer.writeheader()
            for file_metadata in metadata_summary:
                metadata_csv_writer.writerow(file_metadata)


def write_metadata_summary_entry(file_metadata, folder):
    """
    Write an entry in the summary csv file containing metadata from a processed video
    :param file_metadata: the video's metadata
    :param folder: the folder where the csv file is/will be saved
    :return: None
    """
    metadata_file_path = os.path.join(folder, '%s_metadata.csv' % datetime.today().strftime("%Y%m%d"))
    metadata_file_exists = os.path.isfile(metadata_file_path)
    with open(metadata_file_path, 'a') as metadata_csv:
        metadata_csv_writer = csv.DictWriter(metadata_csv, fieldnames=METADATA_CSV_HEADERS)
        if not metadata_file_exists:
            metadata_csv_writer.writeheader()
        metadata_csv_writer.writerow(file_metadata)
