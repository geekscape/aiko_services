#!/usr/bin/env bash
#
# Usage
# ~~~~~
# ./run_publish.sh [frame_delay]
#
# - frame_delay: Seconds between sending frame data
#
# To Do
# ~~~~~
# - None, yet !

# export AIKO_MQTT_HOST=localhost

FRAME_DELAY=${1:-1.0}  # 1.0 / frame_rate

trap ctrl_c_0 INT

function ctrl_c_0() {
  time_end=$(date +%s.%N)
  total_time=$(echo "$time_end - $time_start" | bc)
  frame_rate=$(echo "$frame_id / $total_time" | bc)
  printf "Total time: %.3f, frame rate: %.1f\n" "$total_time" "$frame_rate"
  exit 0
}

frame_id=0
time_start=$(date +%s.%N)

while true; do
  time_now=$(date +%H:%M:%S.%3N)
  echo $time_now: frame: $frame_id

  mosquitto_pub -h $AIKO_MQTT_HOST -t aiko/test -m  \
    "(process_frame (stream_id: 1 frame_id: 0) (i: 0))"

  ((frame_id++))
  sleep $FRAME_DELAY
done
