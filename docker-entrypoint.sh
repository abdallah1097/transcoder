#!/bin/bash

set -x # echo each command before running it.

mount.cifs "$SMB_WATCH" /mount/watch -o user=$SMB_USERNAME,password=$SMB_PASSWORD,vers=3.0,domain=corp.acmi.net.au
mount.cifs "$SMB_ACCESS" /mount/access -o user=$SMB_USERNAME,password=$SMB_PASSWORD,vers=3.0,domain=corp.acmi.net.au
mount.cifs "$SMB_WEB" /mount/web -o user=$SMB_USERNAME,password=$SMB_PASSWORD,vers=3.0,domain=corp.acmi.net.au
mount.cifs "$SMB_MASTER" /mount/master -o user=$SMB_USERNAME,password=$SMB_PASSWORD,vers=3.0,domain=corp.acmi.net.au
mount.cifs "$SMB_OUTPUT" /mount/output -o user=$SMB_USERNAME,password=$SMB_PASSWORD,vers=3.0,domain=corp.acmi.net.au

exec "$@"
