#!/usr/bin/env bash
#
# Watch all MQTT topics
#
# To Do
# ~~~~~
# - Convert to Python and add to "setup.py:entry_points:console_scripts"

AIKO_MQTT_HOST=${1:-${AIKO_MQTT_HOST:-localhost}}

mosquitto_sub -h $AIKO_MQTT_HOST -t '#' -v
