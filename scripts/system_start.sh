#!/bin/bash
#
# Start core Aiko Services
# - mosquitto (MQTT server) ... only start for "localhost"
# - Aiko Registrar
# - Aiko Dasboard
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
