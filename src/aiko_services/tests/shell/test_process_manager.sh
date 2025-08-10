#!/usr/bin/env bash
#
# Usage
# ~~~~~
# ./test_process_manager.sh
#
# To Do
# ~~~~~
# - None, yet !

aiko_process run &
jobs -l

echo --------------------------
echo Aiko ProcessManager Test 0
echo --------------------------
aiko_process create id:0 sleep 9
aiko_process create id:1 sleep 3
aiko_process create id:2 sleep 6
sleep 1
aiko_process dump  # expect all three "sleep" processes
sleep 10
aiko_process dump  # expect all processes exited

echo --------------------------
echo Aiko ProcessManager Test 1
echo --------------------------
aiko_process create id:3 sleep 120
aiko_process dump
aiko_process destroy id:3
sleep 1
aiko_process dump  # expect all processes exited

echo ------------------------
echo Aiko ProcessManager Exit
echo ------------------------

aiko_process exit --grace_time 0
sleep 1
jobs -l
