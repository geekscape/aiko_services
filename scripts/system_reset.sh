#!/usr/bin/env bash
#
# Description
# ~~~~~~~~~~~
# Remove the retained message for locating the primary Aiko Services Registrar
#
# If the MQTT service and/or Aiko Services Registrar are abruptly
# terminated and aren't able to correctly update the Aiko Services Registrar
# "retained message" then subsequent Aiko Sservice Registrars will not promote
# themselves to be the primary Aiko Services Registrar.
#
# Usage
# ~~~~~
# Default MQTT server:    localhost
# Default Aiko namespace: aiko
#
#   ./scripts/system_restart.sh [AIKO_MQTT_HOST] [AIKO_NAMESPACE]
#
# Alternative ...
#   AIKO_MQTT_HOST=<MQTT_HOST_NAME> ./scripts/system_restart.sh
#
# To Do
# ~~~~~
# - Convert to Python and add to "setup.py:entry_points:console_scripts"
# - Test on Linux, Mac OS X and Windows

AIKO_MQTT_HOST=${1:-${AIKO_MQTT_HOST:-localhost}}
AIKO_NAMESPACE=${2:-${AIKO_NAMESPACE:-aiko}}

AIKO_MQTT_TOPIC=$AIKO_NAMESPACE/service/registrar
MQTT_RETAIN=-r
PAYLOAD=

# Empty payload will clear the retained message
mosquitto_pub -h $AIKO_MQTT_HOST -t $AIKO_MQTT_TOPIC $MQTT_RETAIN -m "$PAYLOAD"
