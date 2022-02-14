#!/usr/bin/env python3
#
# Aiko Service: Process Controller
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Create and destroy system processes.
# Not designed to run as part of an Aiko Service Pipeline.
#
# Example usage
# ~~~~~~~~~~~~~
# ./process_controller.py  # run as an Aiko Service
#
# ./process_controller.py --example python
# ./process_controller.py --example shell
#
# To Do
# ~~~~~
# - Check out https://pypi.org/project/python-daemon
#
# - Use of threading versus multiprocessing
#   - https://docs.python.org/2/library/multiprocessing.html
#   - https://hackernoon.com/concurrent-programming-in-python-is-not-what-you-think-it-is-b6439c3f3e6a
#
# - Complete implementation as an Aiko Service
#   - Keep running, even when there are no processes to manage
#   - Query running processes
# - Handle process standard output and standard error

import click
import importlib
import os
import select
import time

from subprocess import Popen
from threading import Thread

PROCESS_POLL_TIME = 0.2  # seconds

import aiko_services.framework as aiko

PROTOCOL = "au.com.silverpond.protocol.process_controller:0"

# --------------------------------------------------------------------------- #

poll = select.poll

class ProcessController(object):
  def __init__(self, handler=None):
    self.handler = handler
    self.processes = {}
    self.thread = None

  def __str__(self):
    output = ""
    for id, process_data in self.processes.items():
      pid = process_data['process'].pid
      command = process_data['command_line'][0]
      if output: output += "\n"
      output += f"{id}: {pid} {command}"
    return output

  def create(self, id, command, arguments=None):
    command_line = [command]
    file_extension = os.path.splitext(command)[-1]
    if file_extension not in [".py", ".sh"]:
      specification = None
      try:
        importlib.util.find_spec
      except AttributeError:  # Python < 3.4
        specification = importlib.find_loader(command)  # pylint: disable=deprecated-method
      else:
        specification = importlib.util.find_spec(command)
      if specification:
        command_line = [specification.origin]
        print("Module path resolved to: '{}'".format(command_line))

    if arguments: command_line.extend(arguments)
    process = Popen(command_line, bufsize=0, shell=False)
    self.processes[id] = {
      "command_line": command_line,
      "process": process,
      "return_code": None
    }

    if not self.thread:
      self.thread = Thread(target=self.run)
      self.thread.start()

  def delete(self, id, terminate=True, kill=False):
    process_data = self.processes[id]
    del self.processes[id]
    process = process_data["process"]
    if terminate: process.terminate()
    if kill: process.kill()
    if self.handler: self.handler(id, process_data)

  def run(self):
    while len(self.processes):
      for id, process_data in list(self.processes.items()):
        process = process_data["process"]
        return_code = process.poll()
        if return_code is not None:
          process_data["return_code"] = return_code
          self.delete(id, terminate=False, kill=False)
      time.sleep(PROCESS_POLL_TIME)

def process_exit_handler(id, process_data):
  details = ""
  if process_data:
    command = process_data['command_line'][0]
    return_code = process_data["return_code"]
    details = f": {command} status: {return_code}"
  print(f"Exit process {id}" + details)

# --------------------------------------------------------------------------- #

def topic_in_handler(aiko, topic, payload_in):
  print(f"Message: {topic}: {payload_in}")

# tokens = payload_in[1:-1].split()
# if len(tokens) >= 1:
#   command = tokens[0]

#   if command == "task" and len(tokens) == 2:
#     operation = tokens[1]
#     if operation == "start":
#       if aks.get_parameter("publish_parameters") == "true":
#         for parameter_name in aks_info.parameters[0]:
#           parameter_value = aks.get_parameter(parameter_name)
#           payload_out = parameter_name + ": " + parameter_value
#           aks_info.mqtt_client.publish(aks_info.TOPIC_OUT, payload_out)

#     payload_out = payload_in
#     mqtt_client.publish(aks_info.TOPIC_OUT, payload=payload_in)

  return False

# --------------------------------------------------------------------------- #

def example_code(process_controller, example):
  if example == "ls":
    command_line = [ "ls", "-l" ]
    process = Popen(command_line, bufsize=0, shell=False)

  if example == "python":
    command = "./process_controller.py"
    arguments = [ "--example", "ls" ]
    process_controller.create("test_1", command, arguments)

  if example == "shell":
    command = "/bin/sh"
    arguments = [ "-c", "echo Start A; sleep  1; echo Stop A" ]
    process_controller.create("A", command, arguments)
    arguments = [ "-c", "echo Start B; sleep  2; echo Stop B" ]
    process_controller.create("B", command, arguments)
    arguments = [ "-c", "echo Start C; sleep 10; echo Stop C" ]
    process_controller.create("C", command, arguments)
    time.sleep(5)
    process_controller.delete("C")

# --------------------------------------------------------------------------- #

@click.command()
@click.option("--example", type=click.STRING, help="Run example")
@click.option("--tags", "-t", type=click.STRING, help="Aiko Service tags")
def main(example, tags):
  global aks_info

  process_controller = ProcessController(process_exit_handler)

  if example:
    example_code(process_controller, example)
  else:
    aiko.set_protocol(PROTOCOL)
    aiko.add_topic_in_handler(topic_in_handler)
#   aiko.parse_tags(tags)
    aiko.process(True)

if __name__ == "__main__":
  main()

# --------------------------------------------------------------------------- #
