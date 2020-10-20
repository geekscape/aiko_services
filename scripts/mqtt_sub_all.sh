#!/bin/sh
#
# Watch all public topics
#
# To Do
# ~~~~~
# - Consider writing in Python and adding to "setup.py:entry_points:console_scripts"

MQTT_HOST=${1:-localhost}

MQTT_TOPIC=$AIKO_NAMESPACE/service/registrar

mosquitto_sub -h $MQTT_HOST -t '#' -v
