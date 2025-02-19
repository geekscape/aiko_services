# Usage
# ~~~~~
# - aiko_pipeline create pipelines/pipeline_arguments.json -fd "()" -ll debug
#
# To Do
# ~~~~~
# - Common system calls, e.g /proc, filesystem, network, etc
# - Update Pipeline Stream Event --> State, implement StateMachine
# - Alter Pipeline Graph control flow
#   - Conditionals

import re
from typing import Tuple

import aiko_services as aiko
from aiko_services.main.utilities import *

__all__ = ["all_outputs", "evaluate", "FunctionArguments"]

# --------------------------------------------------------------------------- #

def all_outputs(pipeline_element, stream):
    frame = stream.frames[stream.frame_id]
    outputs = {}
    for output_definition in pipeline_element.definition.output:
        output_name = output_definition["name"]
        outputs[output_name] = frame.swag[output_name]
    return outputs

# --------------------------------------------------------------------------- #
# FunctionArguments PipelineElement enables modifying process_frame()
# input and output arguments, via "define", "delete" and "rename"
# commands, which are specified as FunctionArguments parameters ...
#
# - define: "(argument_0 expression_0) (argument_1 expression_1) ..."
# - delete: "(argument_0 argument_1 ...)"
# - rename: "(from_0 to_0) (from_1 to_1)"
#
# - expression: expression_0 operator expression_1 ...
# - expression: integer, float, string, list, dictionary, argument_name
# - operator:   +, -, *, /

def evaluate(expression, arguments={}):
    expression = expression.strip()

    if expression in arguments:  # Is an argument ?
        return arguments[expression]

    if re.fullmatch(r"\d+(\.\d+)?", expression):  # Is a number ?
        return float(expression) if "." in expression else int(expression)

    if re.fullmatch(r"\".*\"|\'.*\'" , expression) or expression.isalpha():
        return expression.strip("\"'")  # If present, remove quotes

    if re.fullmatch(r"\[.*\]", expression):
        return eval(expression)  # Convert "list" to a [list]

    match = re.search(r"(\+|\-|\*|/)", expression)  # Binary operation ?
    if match:
        operator = match.group()
        left_expression = expression[:match.start()].strip()
        right_expression = expression[match.end():].strip()

        left_value = evaluate(left_expression, arguments)
        right_value = evaluate(right_expression, arguments)

        if isinstance(left_value, str) and  \
            isinstance(right_value, str) and operator == "+":
            return left_value + right_value

        elif isinstance(left_value, list) and  \
            isinstance(right_value, list) and op == "+":
            return left_value + right_value

        elif isinstance(left_value, (int, float)) and  \
             isinstance(right_value, (int, float)):
            if operator == "+":
                return left_value + right_value
            elif operator == "-":
                return left_value - right_value
            elif operator == "*":
                return left_value * right_value
            elif operator == "/":
                if right_value == 0:
                    raise ValueError("Invalid division by zero")
                return left_value / right_value

    raise ValueError(f"Invalid expression: {expression}")

class FunctionArguments(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("function_arguments:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        swag = stream.frames[stream.frame_id].swag

        for command_name in ["define", "delete", "rename"]:
            command, found = self.get_parameter(command_name)
            if found:
                action, actions = parse(command)
                actions.insert(0, action)
                if command_name == "define" and isinstance(actions, list):
                    for action in actions:
                        self.logger.debug(f"Define: {action}")
                        if isinstance(action[1], str):
                            action[1] = evaluate(action[1], swag)
                        swag[action[0]] = action[1]
                if command_name == "delete" and isinstance(actions, list):
                    for action in actions:
                        self.logger.debug(f"Delete: {action}")
                        if action in swag:
                            del swag[action]
                if command_name == "rename" and isinstance(actions, list):
                    for action in actions:
                        self.logger.debug(f"Rename: {action}")
                        if len(action) == 2 and action[0] in swag:
                            swag[action[1]] = swag.pop(action[0])
        return aiko.StreamEvent.OKAY, all_outputs(self, stream)

# --------------------------------------------------------------------------- #
