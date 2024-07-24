#!/usr/bin/env bash
#
# To Do
# ~~~~~
# - Use discover to find topic_path
# - Combine "action.sh" and "terminate.sh"
# - Create shared code base: common.sh
# - "terminate.sh" option to shutdown robot

AIKO_MQTT_HOST=
ROBOT_HOSTNAME=

PID=`ps ax | grep xgo_robot | grep python3 | grep -v grep | tr -s " " | cut -d" " -f2`
TOPIC_PATH=aiko/$ROBOT_HOSTNAME/$PID/1/in

mosquitto_pub -h $AIKO_MQTT_HOST -t $TOPIC_PATH -m "(terminate)"
