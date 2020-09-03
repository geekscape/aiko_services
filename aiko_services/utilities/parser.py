# To Do
# ~~~~~
# - Implement JSON parsing

from typing import List

__all__ = ["parse"]

def parse(payload: str) -> List:
    tokens = payload[1:-1].split()
    command = ""
    if len(tokens) > 0:
        command = tokens[0]
    parameters = tokens[1:]
    return command, parameters
