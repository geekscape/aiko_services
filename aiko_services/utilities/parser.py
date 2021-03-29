# Notes
# ~~~~~
# Parses ...
# - parse("()")
# - parse("(c)")
# - parse("(c p1 p2)")
# - parse("(add topic protocol owner (a=b c=d))")
#
# Doesn't parse sublists recursively
# Doesn't parse quoted tokens, e.g parse("(c '(not_a_sublist)')")
#
# To Do
# ~~~~~
# - Implement JSON parsing

from typing import List

__all__ = ["parse"]

def parse(payload: str) -> List:
    command = ""
    parameters = []
    tokens = payload[1:-1].split()

    if len(tokens) > 0:
        command = tokens[0]

    sublist = None
    for token in tokens[1:]:
        if not sublist:
            if token.startswith("("):
                if token.endswith(")"):
                    parameters.append(token[1:-1].split())
                else:
                    sublist = [token[1:]]
            else:
                parameters.append(token)
        else:
            if token.endswith(")"):
                sublist.append(token[:-1])
                parameters.append(sublist)
                sublist = None
            else:
                sublist.append(token)

    return command, parameters
