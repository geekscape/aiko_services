#!/usr/bin/env python3
#
# Usage
# ~~~~~
# ./parser.py  # parse() <--> generate() tests for a range of examples
#
# For all operations, the parser() and generate() are each other's inverse
# - parse(generate(atom, list))     --> atom, list
# - generate(parse("s_expression")) --> "s_expression"
#
# Parse lists of symbols recursively
#
# - parse("")
# - parse("()")
# - parse("(c)")
# - parse("(c p1 p2)")
# - parse("(add topic protocol owner (a=b c=d))")
# - parse("('aloha honua')") or parse('("aloha honua")')  # quoted strings
#
# Parse dictionaries with keyword / value pairs
#
# - parse("(a (b: ''))")      --> ("a", [{'b': ""}])
# - parse("(a: 1 b: 2)")      --> {"a": 1, "b": 2}
# - parse("(a: (b c))")       --> {"a": ["b" "c"]}
# - parse("(a: (b: 1 c: 2))") --> {"a": {"b": "1", "c": "2"}}
# - parse("(a: 1 b)")         Illegal: Dictionary and positional parameters
# - parse("(a: 1 (b c) 2)")   Illegal: (b c) should be a dictionary keyword
#
# Parse canonical S-Expressions: binary symbols are prefixed with their length
#   https://en.wikipedia.org/wiki/Canonical_S-expressions
#
# - parse("a 0: b")           --> ["a None b"]
# - parse("3:a b")            --> ["a b"]
# - parse("3:a b 3:c d")      --> ["a b", "c d"]
#
# Doesn't parse plain symbols, i.e anything not in a (list)
# Doesn't parse quoted tokens, e.g parse("(c '(this_is_not_a_list)')") fails
#
# To Do
# ~~~~~
# - Consolidate generate(atom, list) into generate(list)
# - Consolidate parser result "(atom list)" into "list"
#   - Ensure that any S-Expression can be generated and parsed, not only "list"
#
# - Provide proper unit tests !
#
# - Change parse() to simply return the complete tree and ...
#     create new parse_payload() function that returns (command, parameters)
# - Change generate() to simply create the complete S-Expression and ...
#     create new generate_payload() function that returns (command, parameters)
#
# - Implement AVRO schema and JSON parsing, refactor "pipeline.py" ?
# - Incorporate Python module "sexpdata"
#   - https://sexpdata.readthedocs.io/en/latest
#   - https://github.com/jd-boyd/sexpdata
# - Incorporate Python module "hy" and "hyrule"
#
# - Review all places where parse() and generate() are and should be used ...
#   - parse() ...
#       actor.py:     _topic_in_handler()
#       lifecycle.py: _lcm_topic_contol_handler()
#       process.py:    on_registrar()
#       registrar.py: _service_state_handler()
#                     _topic_in_handler()
#       share.py:     _procedure_handler()
#                     _consumer_handler()
#                      registrar_share_handler()
#                      registrar_out_handler()
#       storage.py:   _topic_in_handler()
#                      do_request()
#   - generate() ...
#       Manually "generated" S-Expression payloads everywhere !
#       process.py:   _add_service_to_registrar(): should use generate()
#                     _remove_service_to_registrar(): should use generate()
#       recorder.py:  _recorder_handler(): should use generate()
#       share.py:     _dictionary_to_commands()
#                     _update_consumers(): should use generate()
#       transport/transport_mqtt.py: make_proxy_mqtt()

import re
import sys
from typing import Any, Dict, List, Tuple, Union

__all__ = ["generate", "parse", "parse_float", "parse_int", "parse_number"]

def generate(command: str, parameters: Union[Dict, List, Tuple]) -> str:
    if isinstance(parameters, dict):
        parameters = generate_dict_to_list(parameters)
    elif isinstance(parameters, tuple):
        parameters = list(parameters)
    expression = [command] + parameters
    return generate_s_expression(expression)

def generate_dict_to_list(expression: Dict) -> list:
    result = []
    for keyword, value in expression.items():
        result.append(f"{keyword}:")
        result.append(value)
    return result

RE_DELIMITERS = re.compile(r"^\d+:|[\s()]")

def generate_s_expression(expression: List) -> str:
    character = ""
    payload = "("
    for element in expression:
        if isinstance(element, str):
            if RE_DELIMITERS.search(element):
                element = f"{len(element)}:{element}"
        if isinstance(element, dict):
            element = generate_dict_to_list(element)
        if isinstance(element, list) or isinstance(element, tuple):
            element = generate_s_expression(element)
        if element == "":
            character = ' ""'
        if element is None:
            element = "0:"
        payload = f"{payload}{character}{element}"
        character = " "
    payload = f"{payload})"
    return payload

RE_CANONICAL_SYMBOL = re.compile(r"^(\d+):(.+)", re.DOTALL)  # length:data
RE_STRING = re.compile(r"""(['"])(.*?)\1""")                 # "text" or 'text'

def parse(payload: str, dictionaries_flag=True):
    result = []
    token = ""
    i = 0
    while i < len(payload):
        if not token:
            match = RE_CANONICAL_SYMBOL.match(payload[i:])
            if match:
                token_length = match.group(1)
                if int(token_length) == 0:
                    token = None
                else:
                    token = match.group(2)[:int(token_length)]
                result.append(token)
                token = ""
                i += len(token_length) + 1 + int(token_length)
                continue

            match = RE_STRING.match(payload[i:])
            if match:
                result.append(match.group(2))  # token
                i += len(match.group(0))       # token_length
                continue

        c = payload[i]
        if c == "(":
            sublist, j = parse(payload[i+1:])
            i += j
            result.append(sublist)
        elif c == ")":
            if token:
                result.append(token)
                token = ""
            return result, i+1
        elif c in [" ", "\t", "\n"]:
            if token:
                result.append(token)
                token = ""
        else:
            token += c
        i += 1
    if token:
        result.append(token)

    car = ""
    cdr = []
    if result:
        if isinstance(result[0], str):
            car = result[0]
        else:
            try:
                car = result[0][0]
                cdr = result[0][1:]
            except IndexError:
                pass

    if dictionaries_flag:
        cdr = parse_list_to_dict(cdr)
    return car, cdr

def parse_float(payload: str, default: float=0.0) -> float:
    try:
        result = float(payload)
    except ValueError:
        result = default
    return result

def parse_int(payload: str, default: int=0) -> int:
    try:
        result = int(payload)
    except ValueError:
        result = default
    return result

def parse_list_to_dict(tree: Any) -> Union[list, dict]:
    parse_error = "Error parsing S-Expression dictionary starting at keyword"
    result = tree
    if isinstance(tree, list) and len(tree):
        car = tree[0]
        if isinstance(car, str) and len(car) and car[-1] == ":":
            if len(tree) % 2 != 0:
                raise ValueError(f'{parse_error} "{car}", must have pairs of keywords and values')
            result = {}
            for i in range(len(tree) // 2):
                if not isinstance(tree[i*2], str):
                    raise ValueError(f'{parse_error} "{tree[i*2]}", keyword must be a string')
                if len(tree[i*2]) and tree[i*2][-1] != ":":
                    raise ValueError(f'{parse_error} "{tree[i*2]}", keyword must end with ":" character')
                keyword = tree[i*2][:-1]
                value = parse_list_to_dict(tree[i*2+1])
                result[keyword] = value
        else:
            result = [parse_list_to_dict(element) for element in tree]
    return result

def parse_number(payload: str, default: int=0):
    try:
        result = int(payload)
    except ValueError:
        try:
            result = float(payload)
        except ValueError:
            result = default
    return result

def main():
    payloads = [
    #   "abc",                      # Fails: generate() returns list !
    #   "abc def",                  # Fails: parse() only handles lists
        "(a 0: b)",                 # List containing None (encoded as 0:)
        "(a b ())",                 # List containing empty list
        "(a b (c d))",              # List containing list
        "(a b (c d) (e f (g h)))",  # List containing lists
        "(a b: 1 c: 2)",            # Dictionary
        "(a b: 1 c: (d e))",        # Dictionary containing list
        "(a b: 1 c: (d: 1 e: 2))",  # Dictionary containing dictionary
        "(7:a b c d)",              # Canonical S-Expression list with symbol
        "(3:a b 3:c d)"             # Canonical S-Expression list of symbols
    ]

    for payload_in in payloads:
        command, parameters = parse(payload_in)
        print(f"{payload_in} --> command: {command}, parameters: {parameters}")
        payload_out = generate(command, parameters)
        print(f"{command}, {parameters} --> payload: {payload_out}\n")

if __name__ == "__main__":
    main()
