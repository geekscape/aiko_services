#!/bin/sh
#
# Start core Aiko Services
# - mosquitto (MQTT server)
# - Aiko Registrar
# - Aiko Dasboard
#
# To Do
# ~~~~~
# - Convert to Python and add to "setup.py:entry_points:console_scripts"
# - Test on Linux, Mac OS X and Windows

export AIKO_MQTT_HOST=${1:-localhost}
export AIKO_NAMESPACE=${2:-aiko}

process_start() {
  PROCESS_PATH=$1
	PROCESS_NAME=`basename $PROCESS_PATH`

  PID=`pgrep -x $PROCESS_NAME`
  if [ $? -ne 0 ]; then
	  echo "Starting: $PROCESS_PATH"
    $PROCESS_PATH >/dev/null 2>&1 &
	else
	  echo "Already started: $PROCESS_PATH"
  fi
}

process_start /usr/sbin/mosquitto
process_start aiko_registrar
sleep 2
aiko_dashboard
