#!/usr/bin/env python3
#
# Notes
# ~~~~~
# Parses ...
# - parse("()")
# - parse("(c)")
# - parse("(c p1 p2)")
# - parse("(add topic protocol owner (a=b c=d))")
#
# - parse("(a: 1 b: 2)")      --> {"a": 1, "b": 2}
# - parse("(a: (b c))")       --> {"a": [b c]}
# - parse("(a: (b: 1 c: 2))") --> {"a": {"b": 1, "c": 2}}
# - parse("(a: 1 b)")         Illegal: Dictionary and positional parameters
# - parse("(a: 1 (b c) 2)")   Illegal: (b c) should be a keyword
#
# Doesn't parse quoted tokens, e.g parse("(c '(not_a_sublist)')")
#
# To Do
# ~~~~~
# - Change parse() to simply return the complete tree and ...
#     create new parse_payload() function that returns (command, parameters)
# - Change generate() to simply create the complete S-Expression and ...
#     create new generate_payload() function that returns (command, parameters)
#
# - Incorporate Python module "sexpdata"
#   - https://sexpdata.readthedocs.io/en/latest
#   - https://github.com/jd-boyd/sexpdata
# - Incorporate Python module "hy" and "hyrule"
# - Provide unit tests !
# - Implement AVRO and JSON parsing, refactor "pipeline.py" ?

import sys
from typing import Any, Dict, List, Tuple, Union

__all__ = ["generate", "parse", "parse_int"]

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

def generate_s_expression(expression: List) -> str:
    character = ""
    payload = "("
    for element in expression:
        if isinstance(element, dict):
            element = generate_dict_to_list(element)
        if isinstance(element, list) or isinstance(element, tuple):
            element = generate_s_expression(element)
        payload = f"{payload}{character}{element}"
        character = " "
    payload = f"{payload})"
    return payload

def parse(payload: str, dictionaries_flag=True):
    result = []
    token = ""
    i = 0
    while i < len(payload):
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
    try:
        car = result[0][0]
        cdr = result[0][1:]
    except IndexError:
        pass

    if dictionaries_flag:
        cdr = parse_list_to_dict(cdr)
    return car, cdr

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

def main():
    payloads = [
        "(a b ())",
        "(a b (c d))",
        "(a b (c d) (e f (g h)))",
        "(a b: 1 c: 2)",
        "(a b: 1 c: (d e))",
        "(a b: 1 c: (d: 1 e: 2))"
    ]

    for payload_in in payloads:
        command, parameters = parse(payload_in)
        print(f"{payload_in} --> command: {command}, parameters: {parameters}")
        payload_out = generate(command, parameters)
        print(f"{command}, {parameters} --> payload: {payload_out}\n")

if __name__ == "__main__":
    main()
