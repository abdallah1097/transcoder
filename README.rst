Transcoder
----------

The Collections transcoder mounts network folders and watches for "Master" files, then converts them to a specified "Access" format, then safely (using fixity checks) moves both files into final locations.

The "Access" format is a simple ACMI specification that converts to h.264 and preserves resolution and framerate. This specification can be changed or overridden in ``settings.FFMPEG_ARGS``.

To run on development
---------------------

The Transcoder is shipped as a Docker image. It needs to be run with special permissions to mount the volumes. (The mounting happens in ``docker-entrypoint.sh``). To run, call the following::

   cp dev.tmpl.env dev.env # now edit the values in dev.env
   docker-compose -f docker-compose-dev.yml up --build

To run without Docker::

   virtualenv venv
   source venv/bin/activate
   pip install -r requirements.txt
   env `cat dev.env | grep -v "^#" | xargs` app/easyaccess.py

To install and deploy on Balena
-------------------------------

In Balena, create a new application. Ours is called ``e__transcoder-x86``. Then follow the instructions to install the application on your device/s.

Set your production environment variables in the Balena dashboard - one for every line in the ``.env`` file.

Then, to deploy::

   balena push e__transcoder-x86

Balena uses the ``docker-compose.yml`` file and the ``Dockerfile.template`` file for its deployment.

Valid file names
================
File names follow ACMI Collection naming convention, with components separated by underscores::

   VVVVVVVVVV_tsnn_CamelCaseTitle.ext

In which:

- VVVVVVVVVV is the Vernon ID which is a combination of letters and numbers
   - tsnn is a version identifier, which MUST be lowercase:
   - t is either 'm' for master or 'a' for access copy.
   - s is the scan type 'o' for overscan, 'p' for presentation.
   - nn indicates the version/treatment, e.g. raw, graded, etc.; two numerical digits.
- CamelCaseTitle is a human-readable title that may be ignored by the computer when determining uniqueness.
- ext is the file type, e.g. "mp4" or "mov"

Notes and Assumptions:
======================

- The script only operates on files in the watch folder that are identified as a 'master' file.
- If the process fails at any stage, the rest of the process is skipped; we move on to the next video file.
- Only the Vernon ID and tsnn are used to determine uniqueness. Variations in titles may be ignored.
- MD5 checksum files are created with the same name (including extension) as the file they are identifying with '.md5' appended.
- After the files have been moved into place, ``ffprobe`` is run on both the master and access copies. Various metadata is saved to an associated '.json' file.
- After fixity move of the master file, a copy is fixity-copied to a failsafe folder. This copy will overwrite files of the same name that may be in that folder.
- When a file is being processed, a '.lock' file is created in the same folder, which prevents subsequent process from conflicting. If the script ends prematurely, the lock file will remain in place and will need to be deleted manually.
- In-Slack links need further work. They seem to mount a new folder every time, and may not work on Windows PCs. Let's make a web front-end for this.

TODO:
=====

Sooner:
~~~~~~~
- Will the watch find a file during a move to the watch folder?
- Web front-end for access (or web-safe) copies?

Later:
~~~~~~
- Rather than exit and restart (which exploits Balena), keep folders mounted with automount and run continuously. Note that the list of files to process should be determined every loop to prevent duplicate processing between parallel machines in a farm.
- Show file size, processing time, in Slack
- during a fixity copy: if destination exists, do md5 and no-op if OK.
- Add dry-run param.
