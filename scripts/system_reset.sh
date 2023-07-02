#!/bin/sh
#
# Remove the retained message for locating the primary Service Registrar
#
# To Do
# ~~~~~
# - Convert to Python and add to "setup.py:entry_points:console_scripts"
# - Test on Linux, Mac OS X and Windows

AIKO_MQTT_HOST=${1:-localhost}
AIKO_NAMESPACE=${2:-aiko}

AIKO_MQTT_TOPIC=$AIKO_NAMESPACE/service/registrar
MQTT_RETAIN=-r
PAYLOAD=

# Empty payload will clear the retained message
mosquitto_pub -h $AIKO_MQTT_HOST -t $AIKO_MQTT_TOPIC $MQTT_RETAIN -m "$PAYLOAD"
