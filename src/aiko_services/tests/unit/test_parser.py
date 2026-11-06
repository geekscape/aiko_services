# Usage
# ~~~~~
# pytest [-s] unit/test_parser.py
#
# Unit tests for the S-expression parser (main/utilities/parser.py): what
# generate() writes, parse() reads back unchanged, and a payload that is not
# well formed raises ValueError, never another exception.

import pytest

from aiko_services.main.utilities.parser import generate, parse

@pytest.mark.parametrize("argument", [
    "8080:127.0.0.1:8080",          # digits and a colon: a length prefix
    "localhost:8080:127.0.0.1:8080",
    "12:30",
    "two words",
    "(parenthesis)",
    "plain",
])
def test_generate_then_parse_round_trips_an_argument(argument):
    payload = generate("response", ["000003", "7216", "ssh", "-L", argument])
    command, arguments = parse(payload)
    assert command == "response"
    assert arguments == ["000003", "7216", "ssh", "-L", argument]

def test_a_length_prefix_longer_than_the_payload_is_a_value_error():
    """The ProcessManager published this before its reply used generate()"""

    with pytest.raises(ValueError, match="Length prefix"):
        parse("(response 000003 7216 ssh -L 8080:127.0.0.1:8080 devops@host)")

def test_an_unquoted_time_is_a_value_error():
    with pytest.raises(ValueError):
        parse("(log 12:30 lunch)")

def test_a_list_without_its_closing_parenthesis_is_a_value_error():
    with pytest.raises(ValueError, match="closing"):
        parse("(text 0 0 hello")
    with pytest.raises(ValueError, match="closing"):
        parse("(a (b c) (d e)")

def test_well_formed_payloads_are_unchanged():
    assert parse("(text 0 0 hello)") == ("text", ["0", "0", "hello"])
    assert parse('(text 0 0 "12:30")') == ("text", ["0", "0", "12:30"])
    assert parse("(a (b c) d)") == ("a", [["b", "c"], "d"])
    assert parse("(list topic 0:)") == ("list", ["topic", None])
    assert parse("(item 5:a b c)") == ("item", ["a b c"])
