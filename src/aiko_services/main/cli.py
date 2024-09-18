#!/usr/bin/env python3
#
# Aiko Service: Command Line Interface
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# aiko <pipeline_definition_pathname> [--help]
#
# Description
# ~~~~~~~~~~~
# The Pipeline CLI is designed to slip ontop of existing
# pipeline definitions. I learn best with an exaple:
#
# pipeline_definition = [
#     {   "name": "VideoReadFile", "module": "aiko_services.media.video_id",
#         "successors": ["VideoWriteFile"],
#         "parameters": {
#             "video_pathname": "my-video.mp4,
#         }
#     },
#     {   "name": "VideoWriteFile", "module": "aiko_services.media.video_id",
#         "parameters": {
#             "output_pathname": "out-video.mp4,
#         }
#     },
# ]
#
# Out-of-the-box the CLI wrapper will treat everything as an optional
# parameter. To do this it infers some attributes for convenience. To
# override them create another paramerter with the same name appended
# with "_cli" and a dict of updated values.
#
#   "name": Overrides the cli parameter names
#     default: infered from component Name and parameter name
#     eg: --video-read-file-video-pathname
#     override: {"name": "-v --video-path"}
#     notes: separate short "-x" and long "--xxx" form with a space " "
#            can provide one or the other.
#
#   "required": Makes the parameter a required param from the cli
#      default: False
#      override: {"required": True}
#
#   "help": Help string
#     default: infered from component Name and parameter name
#     eg: Overrides VideoReadFile.video_pathname
#     override: {"help": "some help string"}
#
#   "hidden": Hide from CLI
#      default: False
#      override: {"hidden": True}
#
# Full Example:

# pipeline_definition = [
#     {   "name": "SomeComponent", "module": "some.module",
#         "successors": ["NextComponent"],
#         "parameters": {
#             "some_param": "default_value.mp4",
#             "some_param_cli": {
#               "name": "-v --video",
#               "help": "Better help string",
#             },
#
#             "hidden_param": "another_value.txt",
#             "hidden_param_cli": {"hidden": True}
#         }
#     },
# ]
#
# ToDo:
#   - Move --show to shim so Click doesn't complain about required params

import click
import re
import sys
import yaml
import json

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = []

MATCH_CAMEL_CASE = re.compile(r"(?<!^)(?=[A-Z])")
DEFAULT_PIPELINE_NAME = "pipeline_definition"
DEFAULT_PIPELINE_FRAME_RATE = 0.05 # 20 FPS, 0 for flat-out!
SEP = "_SEP_"
pipeline_definition = []


def to_snake_case(val):
  return MATCH_CAMEL_CASE.sub("_", val).lower()

def cli_shim():
    """
    Intercept the cli args and determine if a path to a pipeline definition
    was passed. If so, pull it out and load it before Click gets it grubby
    little hands on it.
    """
    if len(sys.argv) >= 2 and sys.argv[1].endswith((".py", ".yaml", ".yml", ".json")):
        pipeline_definition_pathname = sys.argv[1]
        pipeline_definition, state_machine_model = load_pipeline_definition_2020(pipeline_definition_pathname)
        sys.argv.remove(pipeline_definition_pathname)
    else:
        pipeline_definition = []
        sys.argv = ["aiko", "--help"]

    return pipeline_definition


def options_from_pipeline_def(pipeline_definition):
    """
    Cli with default:

      param_name: <param> # Pipeline default
      param_name_cli: {
        "hidden": True,
        "name": # Optionally say how flags appear on cli. ie "-o --output-path"
        "required": # True|False. Default: False
        "help":      # Optional help string

        ""
        }


    """
    def infer_help(component_name, param_name):
        help_str = f"Overrides {component_name}.{param_name}"
        #if value is not None:
        #    help_str += f" [{value}]"
        return help_str

    def infer_flag(component_name, param_name):
        snake_name = to_snake_case(component_name)
        return f"--{snake_name}-{param_name}".replace("_","-").replace(" ", "-")

    def validate_attributes(attributes, component_name, param_name):
        valid_attrs = {
            "required": bool,
            "name": str,
            "help": str,
            "hidden": bool,
        }
        for k,v in attributes.items():
            if k not in valid_attrs:
                ks = list(valid_attrs.keys())
                msg = (
                    f"Invalid cli attribute {component_name}.{param_name}. "
                    f"Got: {k}. Valid attributes are {ks}.")
                raise ValueError(msg)

    def validate_value_type(value, attributes, component_name, param_name):
        if not isinstance(value, attributes["type"]):
            t = attributes["type"]
            msg = (
                f"Type missmatch in {component_name}.{param_name} "
                f"type of {t} specified, but got {type(value)}"
            )
            raise ValueError(msg)


    def decorator(f):
        for ele in reversed([e for e in pipeline_definition if "parameters" in e]):
            component_name = ele["name"]

            # Required cli params
            params = {k:v for k,v in ele["parameters"].items() if not k.endswith("_cli")}
            cli_attrs = {k:v for k,v in ele["parameters"].items() if k.endswith("_cli")}
            for param_name, value in params.items():
                attributes = cli_attrs.pop(f"{param_name}_cli", {})
                if attributes.get("hidden", False):
                    continue
                validate_attributes(attributes, component_name, param_name)

                # Fill in missing attributes as needed
                if not attributes.get("required", False):
                    attributes["default"] = value
                    attributes["show_default"] = True


                attributes["type"] = type(value)
                if "help" not in attributes:
                    attributes["help"] = infer_help(component_name, param_name)

                infered_flag = infer_flag(component_name, param_name)
                flags = attributes.get("name", infered_flag).split()

                validate_value_type(value, attributes, component_name, param_name)
                variable_name = f"{component_name}{SEP}{param_name}"
                flags += [variable_name]
                click.option(*flags, **attributes)(f)
        return f
    return decorator


def clean_cli_params(pipeline_definition):
    for component in [e for e in pipeline_definition if "parameters" in e]:
        param_names = list(component["parameters"].keys())
        for param_name in param_names:
            if param_name.endswith("_cli"):
                component["parameters"].pop(param_name)
    return pipeline_definition

pipeline_definition = cli_shim()

@click.command("main", help=(
  "Load Pipeline Definition, build cli, override parameters if needed, run "
  "pipeline. Like a boss!\n\nUsage:\n\n"

  "  aiko <pipeline_definition.py> --help"))
@options_from_pipeline_def(pipeline_definition)
@click.option("--pipeline-frame-rate", "-fps", type=int,
  required=False, default=DEFAULT_PIPELINE_FRAME_RATE,
  help=f"Rate at which to run the pipeline over frames [{DEFAULT_PIPELINE_FRAME_RATE}]")
@click.option("--show", is_flag=True,
  help="Only print the pipeline, dont run it.")
@click.option("--dump", type=str, default=None,
  help="Save the file to yaml or json")

def main(**kwargs):
    dump = kwargs["dump"]
    if dump is not None:
        to_dump = {"pipeline_definition": pipeline_definition}
        if dump.endswith((".yaml", ".yml")):
            with open(dump, "w") as f:
                yaml.dump(to_dump, f)
        elif dump.endswith(".json"):
            with open(dump, "w") as f:
                json.dump(to_dump, f, indent=2)
        else:
            raise ValueError(f"Invalid file type: got {dump}")
        return 0

    _pipeline_def = clean_cli_params(pipeline_definition)
    pipeline = Pipeline_2020(_pipeline_def, kwargs["pipeline_frame_rate"])

    for k,v in kwargs.items():
        if SEP in k:
            node_name, param_name = k.split(SEP)
            pipeline.update_node_parameter(node_name, param_name, v)

    if kwargs["show"]:
        d = []
        for node in _pipeline_def:
            node_name = node["name"]
            info = pipeline.get_node(node_name)
            d.append({
                "name": node_name,
                "module": info["module"],
                "successors": info["successors"],
                "parameters": info["parameters"]
            })
        print(yaml.dump(d))
    else:
        pipeline.run(mqtt_connection_required=False)

if __name__ == "__main__":
    main()
