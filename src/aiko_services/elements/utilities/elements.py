# Usage
# ~~~~~
# - aiko_pipeline create pipelines/pipeline_expression.json -fd "()" -ll debug
#
# To Do
# ~~~~~
# - Expression evaluation support ...
#   - Dictionary or List access, e.g variable[1] or variable[index]
#     - Requires parser improvement for list[index], e.g variable[index]
#   - Extensible list of functions, e.g random(), stack push() / pop()
#     - Requires parser improvement for function calls, e.g random()
#
# - Common system calls, e.g /proc, filesystem, network, etc
# - Update Pipeline Stream Event --> State, implement StateMachine
# - Alter Pipeline Graph control flow
#   - Conditionals

import re
from typing import Tuple

import aiko_services as aiko
from aiko_services.main.utilities import *

__all__ = [
    "all_outputs", "evaluate", "evaluate_conition", "evaluate_define",
    "Expression"
]

# --------------------------------------------------------------------------- #

def all_outputs(pipeline_element, stream):
    frame = stream.frames[stream.frame_id]
    outputs = {}
    for output_definition in pipeline_element.definition.output:
        output_name = output_definition["name"]
        outputs[output_name] = frame.swag[output_name]
    return outputs

# --------------------------------------------------------------------------- #
# Expression PipelineElement enables modifying process_frame()
# input and output arguments, via "define", "delete" and "rename"
# commands, which are specified as Expression parameters ...
#
# - define: "(argument_0 expression_0) (argument_1 expression_1) ..."
# - delete: "(argument_0 argument_1 ...)"
# - rename: "(from_0 to_0) (from_1 to_1)"
#
# - expression: expression_0 operator expression_1 ...
# - expression: integer, float, string, list, dictionary, argument_name
# - operator:   + - * / < <= > >=

def evaluate(expression, arguments={}):
    expression = expression.strip()

    if expression in arguments:  # Is an argument ?
        return arguments[expression]

    if re.fullmatch(r"\d+(\.\d+)?", expression):  # Is a number ?
        return float(expression) if "." in expression else int(expression)

    if re.fullmatch(r"\".*\"|\'.*\'" , expression) or  \
        re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", expression):
        return expression.strip("\"'")  # If present, remove quotes

    if re.fullmatch(r"\[.*\]", expression):
        return eval(expression)  # Convert "list" to a [list]

    match = re.search(r"(\+|\-|\*|/|\<|\<=|/>|\>=)", expression)  # operators
    if match:
        operator = match.group()
        left_expression = expression[:match.start()].strip()
        right_expression = expression[match.end():].strip()

        left_value = evaluate(left_expression, arguments)
        right_value = evaluate(right_expression, arguments)

        left_value = parse_number(left_value, left_value)     # coerce to number
        right_value = parse_number(right_value, right_value)  # ditto

        if isinstance(left_value, (int, float)) and  \
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
            elif operator == "<":
                return left_value < right_value
            elif operator == "<=":
                return left_value <= right_value
            elif operator == ">":
                return left_value > right_value
            elif operator == ">=":
                return left_value >= right_value

        elif operator == "+" and  \
             isinstance(left_value, list) and isinstance(right_value, list):
            return left_value + right_value

        elif operator == "+" and  \
             isinstance(left_value, (int, float, str)) and  \
             isinstance(right_value, (int, float, str)):
            return f"{left_value}{right_value}"

    return expression  # Treat everything else as a "string"
#   raise ValueError(f"Invalid expression: {expression}")

def evaluate_condition(expressions, swag, logger=None):
    results = []
    if isinstance(expressions, list):
        for expression in expressions:
            if logger:
                logger.debug(f"Expression: {expression}")
            if isinstance(expression[0], str):
                expression[0] = evaluate(expression[0], swag)
            results.append(True if expression[0] else False)
    return all(results)

def evaluate_define(expressions, swag, logger=None, name="Define"):
    if isinstance(expressions, list):
        for expression in expressions:
            if logger:
                logger.debug(f"{name}: {expression}")
            if isinstance(expression[1], str):
                expression[1] = evaluate(expression[1], swag)
            swag[expression[0]] = expression[1]

class Expression(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("expression:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        swag = stream.frames[stream.frame_id].swag

        for command_name in ["define", "delete", "rename"]:
            command, found = self.get_parameter(command_name)
            if found:
                expressions = parse(command, car_cdr=False)
                if command_name == "define":
                    evaluate_define(expressions, swag, self.logger)
                if command_name == "delete" and isinstance(expressions, list):
                    for name in expressions:
                        self.logger.debug(f"Delete: {name}")
                        if name in swag:
                            del swag[name]
                if command_name == "rename" and isinstance(expressions, list):
                    for name in expressions:
                        self.logger.debug(f"Rename: {name}")
                        if len(name) == 2 and name[0] in swag:
                            swag[name[1]] = swag.pop(name[0])
        return aiko.StreamEvent.OKAY, all_outputs(self, stream)

# --------------------------------------------------------------------------- #
