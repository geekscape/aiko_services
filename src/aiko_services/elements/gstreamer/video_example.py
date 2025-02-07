#!/usr/bin/env python3
#
# Usage
# ~~~~~
# ./video_example.py -if input_filename      -of output_filename  \
#   -r width height -f framerate [-cv]
#
# ./video_example.py -is input_hostname:port -os output_hostname:port  \
#   -r width height -f framerate -cv  [--RTP]
#
# ./video_example.py -if input_filename      -os output_hostname:port  \
#   -r width height -f framerate -cv
#
# ./video_example.py -is input_hostname:port -of output_filename  \
#   -r width height -f framerate -cv  [--RTP]
#
# ./video_example.py -if ../data/football_test_0.mp4 -os 192.168.1.65:5000  \
#   -r 1280 720 -f 30/1 -cv
#
# CAMERA_IP=192.168.1.89:554
# CAMERA_IP=192.168.1.105:554
# TARGET_IP=192.168.1.155:5000
#
# Default is RTSP protocol, use "--RTP" option to use RTP protocol
# ./video_example.py -is $CAMERA_IP -os $TARGET_IP -r 640 480 -f 25/1 -cv
#
# To Do
# ~~~~~
# - Turn this into a CI test !

import argparse
import sys

from aiko_services.elements.gstreamer import *

# --------------------------------------------------------------------------- #

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("-if", "--input_filename", type=str, default="",
    help="Video input filename")
  parser.add_argument("-is", "--input_stream", type=str, default="",
    help="Video input hostname:port")
  parser.add_argument("-of", "--output_filename", type=str, default="",
    help="Video output filename")
  parser.add_argument("-os", "--output_stream", type=str, default="",
    help="Video output hostname:port")
  parser.add_argument("-r", "--resolution", type=str, default="", nargs=2,
    help="Video resolution width and height")
  parser.add_argument("-f", "--framerate", type=str, default="",
    help="Video resolution width and height")
  parser.add_argument("-cv", "--opencv",
    action='store_true', help="Display on local display and overlay frame id")
  parser.add_argument("--RTP",
    action='store_true', help="Use RTP protocol")
  args = parser.parse_args()

  width, height = args.resolution

  if args.opencv: utilities.enable_opencv()

  if (args.input_filename == "" and args.input_stream == "") or  \
     (args.input_filename != "" and args.input_stream != ""):
    print("usage: Must provide one of either input filename or hostname:port")
    sys.exit(-1)

  if (args.output_filename == "" and args.output_stream == "") or  \
     (args.output_filename != "" and args.output_stream != ""):
    print("usage: Must provide one of either output filename or hostname:port")
    sys.exit(-1)

  try:
    if args.input_filename != "":
      video_reader = VideoFileReader(args.input_filename, width, height)
    else:
      try:
        input_hostname, input_port = args.input_stream.split(":")
      except ValueError as exception:
        print("Error: please specify input as hostname:port")
        sys.exit(-1)
      video_reader = VideoStreamReader(input_hostname, input_port, width, height, rtp=args.RTP)

    if args.output_filename != "":
      video_writer = VideoFileWriter(args.output_filename, width, height, args.framerate)
    else:
      try:
        output_hostname, output_port = args.output_stream.split(":")
      except ValueError as exception:
        print("Error: please specify output as hostname:port")
        sys.exit(-1)
      video_writer = VideoStreamWriter(output_hostname, output_port, width, height, args.framerate)

    utilities.process_video(video_reader, video_writer)

  except ValueError as exception:
    print("Error: " + str(exception))

  except GStreamerError as exception:           # TODO: Needs better diagnostic
    print("GStreamer Error: " + str(exception))

# --------------------------------------------------------------------------- #
