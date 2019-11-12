"""
ACMI collection item files have the format::

    VERNONID_xxdd_TitleInCamelCase.ext

and folders have the format::

    VERNONID_TitleInCamelCase


This files has tools for extracting Vernon ID, XXXX and Title from file paths.
"""
import os
import posixpath
import re
from urllib.parse import urljoin

import settings

FILE_REGEX = r"([a-zA-Z0-9]+)_([ma][a-z]\d\d)_(.+)"
FOLDER_REGEX = r"([a-zA-Z0-9]+)_(.+)"


def parse_collection_file_path(path):
    """
    Return a tuple of Vernon ID, XXXX and Title.
    """
    filename = os.path.basename(path)
    basename = os.path.splitext(filename)[0]
    parts = re.match(FILE_REGEX, basename)

    if parts:
        groups = parts.groups()
        return groups
    else:
        raise ValueError("Can't find Vernon ID, type and title in '%s'." % filename)

def parse_collection_folder_path(path):
    """
    Return a tuple of Vernon ID and Title.
    """
    if path.endswith(os.sep):
        path = path[:-1]
    basename = os.path.basename(path)
    parts = re.match(FOLDER_REGEX, basename)

    if parts:
        return parts.groups()
    else:
        raise ValueError("Can't find Vernon ID and title in '%s'." % basename)


def get_or_create_collection_folder(filename, parent=None):
    vernon_id, _, title = parse_collection_file_path(filename)

    # return a folder that starts with vernon_id in parent, if one exists; otherwise create it.
    if parent:
        parent = os.path.abspath(os.path.expanduser(parent))
        for dir in os.listdir(parent):
            if dir.startswith(vernon_id):
                return os.path.join(parent, dir)

        # didn't find one; create it.
        new_path = os.path.join(parent, "%s_%s" % (vernon_id, title))
        os.makedirs(new_path)
        return new_path
    else:
        return "%s_%s" % (vernon_id, title)


def master_to_access_filename(master_path, extension=".mp4"):
    """
    :param master_path: a master filename, with or without folder
    :param extension: the desired extension of the result.
    :return: the desired filename of the equivalent access file, without folder name. e.g. "/my/folder/123456_mp01_MyTitle.mov" => "123456_ap01_MyTitle.mp4"
    """

    id, type, title = parse_collection_file_path(master_path)

    type_char = type[0]
    try:
        assert type_char == "m"
    except AssertionError:
        raise ValueError("%s is not named like a master file." % master_path)

    return "%s_%s%s_%s%s" % (id, 'a', type[1:], title, extension)


def abspath(p):
    return os.path.abspath(os.path.expanduser(p))


def file_path_to_url(file_path):
    full_path = abspath(file_path)
    commonpath = os.path.commonpath([full_path, settings.MASTER_FOLDER])
    if os.path.samefile(commonpath, settings.MASTER_FOLDER):
        url_root = settings.MASTER_URL
    else:
        commonpath = os.path.commonpath([full_path, settings.ACCESS_FOLDER])
        if os.path.samefile(commonpath, settings.ACCESS_FOLDER):
            url_root = settings.ACCESS_URL
        else:
            raise ValueError("%s doesn't seem to be in either the Master or Access folders. Not sure how to make a URL for this." % file_path)

    diffpath = full_path[len(commonpath):].lstrip(posixpath.sep)
    return posixpath.join(url_root, diffpath)
