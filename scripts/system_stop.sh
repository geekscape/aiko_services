#!/usr/bin/env bash
#
# Description
# ~~~~~~~~~~~
# Stops the core Aiko Services ...
# - mosquitto  # MQTT server: only stop when run on "localhost"
# - aiko_registrar
#
# Usage
# ~~~~~
# Default MQTT server:    localhost
# Default Aiko namespace: aiko
#
#   ./scripts/system_stop.sh [AIKO_MQTT_HOST] [AIKO_NAMESPACE]
#
# Alternative ...
#   AIKO_MQTT_HOST=<MQTT_HOST_NAME> ./scripts/system_stop.sh
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

process_stop() {
  PROCESS_PATH=$1
  PROCESS_NAME=`basename $PROCESS_PATH`

  PID=`pgrep $PGREP_ARGUMENT $PROCESS_NAME`
  if [ $? -eq 0 ]; then
    echo "Stopping: $PROCESS_PATH"
    kill $PID
  else
    echo "Already stopped: $PROCESS_PATH"
  fi
}

process_stop aiko_registrar

if [ $AIKO_MQTT_HOST == "localhost" ]; then
  process_stop $MOSQUITTO_COMMAND
else
  echo "Won't stop remote $MOSQUITTO_COMMAND"
fi
