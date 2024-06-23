#!/bin/bash
#
# Description
# ~~~~~~~~~~~
# Starts the core Aiko Services ...
# - mosquitto  # MQTT server: only start when run on "localhost"
# - aiko_registrar
# - aiko_dashboard
#
# Usage
# ~~~~~
# Default MQTT server:    localhost
# Default Aiko namespace: aiko
#
#   ./scripts/system_start.sh [AIKO_MQTT_HOST] [AIKO_NAMESPACE]
#
# Alternative ...
#   AIKO_MQTT_HOST=<MQTT_HOST_NAME> ./scripts/system_start.sh
#
# To Do
# ~~~~~
# - Convert to Python and add to "setup.py:entry_points:console_scripts"
#   - Test on Linux, Mac OS X and Windows

export AIKO_MQTT_HOST=${1:-${AIKO_MQTT_HOST:-localhost}}
export AIKO_NAMESPACE=${2:-${AIKO_NAMESPACE:-aiko}}

if [ `uname` == "Darwin" ]; then
  MOSQUITTO_COMMAND=/usr/local/sbin/mosquitto
  PGREP_ARGUMENT=-f
else
  MOSQUITTO_COMMAND=/usr/sbin/mosquitto
  PGREP_ARGUMENT=-x
fi

process_start() {
  PROCESS_PATH=$1
  PROCESS_NAME=`basename $PROCESS_PATH`

  PID=`pgrep $PGREP_ARGUMENT $PROCESS_NAME`
  if [ $? -ne 0 ]; then
	  echo "Starting: $PROCESS_PATH"
    $PROCESS_PATH >/dev/null 2>&1 &
  else
    echo "Already started: $PROCESS_PATH"
  fi
}

if [ $AIKO_MQTT_HOST == "localhost" ]; then
  process_start $MOSQUITTO_COMMAND
else
  echo "Won't start remote $MOSQUITTO_COMMAND"
fi

process_start aiko_registrar

sleep 2
aiko_dashboard
