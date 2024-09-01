#!/usr/bin/env bash
#
# Usage
# ~~~~~
# ./run_small.sh [WARNING|INFO|DEBUG] [true|false] [frame_delay]
#
# ./run_small.sh WARNING true 0.02  # maximum frame rate before falling behind
#
# - WARNING: Default: No log messages
# - INFO:    Shows application log messages
# - DEBUG:   Shows PE_Metrics log measurements
#
# - true:    Default: MQTT logging
# - false:   Console logging
#
# - frame_delay: Seconds between sending frame data
#
# To Do
# ~~~~~
# - Determine what is limiting the maximum frame rate to be 50 Hz
# - Suport multiple concurrent Streams
# - Support unlimited number of Pipelines (using looping to start them)

# export AIKO_MQTT_HOST=localhost

export AIKO_LOG_LEVEL=${1:-WARNING}
export AIKO_LOG_MQTT=${2:-all}
FRAME_DELAY=${3:-1.0}                # 1.0 / frame_rate

USE_PIPELINE=a  # or b, c

GRACE_TIME=10
STREAM_ID=1

process_frame=true

trap ctrl_c_0 INT

function ctrl_c_0() {
  trap ctrl_c_1 INT
  echo "  Pipelines still running, frame generation stopped"
  process_frame=false
}

function ctrl_c_1() {
  echo "  Exit"
  kill $process_ids
  exit 0
}

process_ids=""
for pipeline_id in a b c; do
  pipeline_name=pipeline_small_${pipeline_id}
  aiko_pipeline create ${pipeline_name}.json &
  # aiko_pipeline create ${pipeline_name}.json 2>${pipeline_name}.log &
  process_id=$!
  process_ids="$process_ids $process_id"
  export topic_pipeline_${pipeline_id}=aiko/$HOSTNAME/$process_id/1/in
done

use_topic_name=topic_pipeline_${USE_PIPELINE}
use_topic=${!use_topic_name}

# while true; do sleep 1.0; done  # stop for all Pipelines to start-up
sleep 1.0  # wait for Pipelines to start-up

mosquitto_pub -h $AIKO_MQTT_HOST -t $use_topic -m  \
  "(create_stream $STREAM_ID () $GRACE_TIME)"
# sleep 2.0  # wait for Streams to be created

frame_id=0
while true; do
  if [[ $process_frame == true ]]; then
    echo Frame: $frame_id
    mosquitto_pub -h $AIKO_MQTT_HOST -t $use_topic -m  \
      "(process_frame (stream_id: $STREAM_ID frame_id: $frame_id) (i: 0))"
    ((frame_id++))
  fi
  sleep $FRAME_DELAY
done
