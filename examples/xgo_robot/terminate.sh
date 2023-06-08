#!/bin/bash

AIKO_MQTT_HOST=geekscape.freeddns.org
ROBOT_HOSTNAME=laika

PID=`ps ax | grep xgo_robot | grep python3 | grep -v grep | tr -s " " | cut -d" " -f2`
TOPIC_PATH=aiko/$ROBOT_HOSTNAME/$PID/1/in

mosquitto_pub -h $AIKO_MQTT_HOST -t $TOPIC_PATH -m "(terminate)"
