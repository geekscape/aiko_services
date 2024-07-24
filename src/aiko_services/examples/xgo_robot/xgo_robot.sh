#!/usr/bin/env bash

cd $HOME
source venv/bin/activate
export PYTHONPATH=$HOME/aiko_services:$HOME/cm4-main
export AIKO_MQTT_HOST=

cd aiko_services/examples/xgo_robot
./xgo_robot.py
