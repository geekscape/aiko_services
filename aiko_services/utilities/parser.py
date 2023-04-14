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
# Doesn't parse quoted tokens, e.g parse("(c '(not_a_sublist)')")
#
# To Do
# ~~~~~
# - Incorporate Python module "sexpdata"
#   - https://sexpdata.readthedocs.io/en/latest
#   - https://github.com/jd-boyd/sexpdata
# - Incorporate Python module "hy" and "hyrule"
# - Provide unit tests !
# - Implement JSON parsing

import sys
from typing import List, Tuple, Union                 
                                         
__all__ = ["generate", "parse", "parse_int"]
                  
def generate(command: str, parameters: Union[List, Tuple]) -> str:
    expression = [command] + list(parameters)
    return generate_s_expression(expression)
                           
def generate_s_expression(expression: List) -> str:
    character = ""                        
    payload = "("                                
    for element in expression:
        if type(element) in [list, tuple]:
            element = generate_s_expression(element)
        payload = f"{payload}{character}{element}"
        character = " "
    payload = f"{payload})"
    return payload

def parse(payload: str):
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
    return car, cdr

def parse_int(payload: str, default: int=0) -> int:
    try:
        result = int(payload)
    except ValueError:
        result = default
    return result

def main():
    payloads = [ "(a b ())", "(a b (c d))" ]

    for payload_in in payloads:
        command, parameters = parse(payload_in)
        print(f"{payload_in} --> command: {command}, parameters: {parameters}")
        payload_out = generate(command, parameters)
        print(f"{command}, {parameters} --> payload: {payload_out}\n")

if __name__ == "__main__":
    main()
