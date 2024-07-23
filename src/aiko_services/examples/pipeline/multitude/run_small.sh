#!/bin/bash
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

export AIKO_LOG_LEVEL=${1:-WARNING}
export AIKO_LOG_MQTT=${2:-true}
export FRAME_DELAY=${3:-1.0}      # 1.0 / frame_rate

export USE_PIPELINE=a  # or b, c

export GRACE_TIME=10
export STREAM_ID=1

export process_frame=true

trap ctrl_c_0 INT

function ctrl_c_0() {
  trap ctrl_c_1 INT
  echo "  Pipelines still running, frame generation stopped"
  export process_frame=false
}

function ctrl_c_1() {
  echo "  Exit"
  pkill aiko_pipeline  # CAUTION: Indiscriminately kills Aiko Pipelines !
  exit 0
}

for pipeline_id in a b c; do
  pipeline_name=pipeline_small_${pipeline_id}
  aiko_pipeline create ${pipeline_name}.json &
  # aiko_pipeline create ${pipeline_name}.json 2>${pipeline_name}.log &
  export topic_pipeline_${pipeline_id}=aiko/spike/$!/1/in
done

export use_topic_name=topic_pipeline_${USE_PIPELINE}
export use_topic=${!use_topic_name}

# while true; do sleep 1.0; done  # stop for all Pipelines to start-up
sleep 1.0  # wait for Pipelines to start-up

mosquitto_pub -t $use_topic -m "(create_stream $STREAM_ID () $GRACE_TIME)"
# sleep 2.0  # wait for Streams to be created

frame_id=0
while true; do
  if [[ $process_frame == true ]]; then
    echo Frame: $frame_id
    mosquitto_pub -t $use_topic -m  \
      "(process_frame (stream_id: $STREAM_ID frame_id: $frame_id) (i: 0))"
    ((frame_id++))
  fi
  sleep $FRAME_DELAY
done
