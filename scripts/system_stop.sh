#!/bin/sh
#
# Stop core Aiko Services
# - mosquitto (MQTT server)
# - Aiko Registrar
#
# To Do
# ~~~~~
# - Convert to Python and add to "setup.py:entry_points:console_scripts"

export AIKO_MQTT_HOST=${1:-localhost}
export AIKO_NAMESPACE=${2:-aiko}

process_stop() {
  PROCESS_PATH=$1
	PROCESS_NAME=`basename $PROCESS_PATH`

  PID=`pgrep -x $PROCESS_NAME`
  if [ $? -eq 0 ]; then
	  echo "Stopping: $PROCESS_PATH"
		kill $PID
	else
	  echo "Already stopped: $PROCESS_PATH"
  fi
}

process_stop aiko_registrar
process_stop /usr/sbin/mosquitto
