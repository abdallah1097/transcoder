#!/bin/bash

while true
do
cd ~/transcoder/ && docker-compose -f docker-compose-dev.yml up --build >> ~/transcoder_log.txt
done
