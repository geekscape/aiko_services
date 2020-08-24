#!/bin/sh
#
# Remove the retained message for locating the primary Service Registrar
#
# To Do
# ~~~~~
# - Consider writing in Python and adding to "setup.py:entry_points:console_scripts"

MQTT_HOST=${1:-localhost}
AIKO_NAMESPACE=${2:-test}

MQTT_TOPIC=$AIKO_NAMESPACE/service/registrar
MQTT_RETAIN=-r
# Empty payload will clear the retained message
PAYLOAD=

mosquitto_pub -h $MQTT_HOST -t $MQTT_TOPIC $MQTT_RETAIN -m "$PAYLOAD"
