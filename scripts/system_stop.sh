#!/bin/bash
#
# Stop core Aiko Services
# - mosquitto (MQTT server) ... only stop for "localhost"
# - Aiko Registrar
#
# To Do
# ~~~~~
# - Convert to Python and add to "setup.py:entry_points:console_scripts"
#   - Test on Linux, Mac OS X and Windows

export AIKO_MQTT_HOST=${1:-localhost}
export AIKO_NAMESPACE=${2:-aiko}

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
