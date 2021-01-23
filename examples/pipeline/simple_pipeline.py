from aiko_services.pipeline import Pipeline

ELEMENTS_SIMPLE = "aiko_services.elements.simple"

pipeline_definition = [
    {
        "name": "RandInt",
        "module": ELEMENTS_SIMPLE,
        "successors": ["MathList"],
        "parameters": {
            # "list_len": 5,   # Defaults are defined in definition
            # "iterations": 2, # un comment to override
            # "min": 30,
            # "max": 100,
        },
    },
    {
        "name": "MathList",
        "module": ELEMENTS_SIMPLE,
        "parameters": {
            "operation": "add",
        },
        "inputs": {"numbers": ["RandInt", "list"]},
        "successors": ["Print"],
    },
    {
        "name": "Print",
        "module": ELEMENTS_SIMPLE,
        "parameters": {
            "message_1": "The random ints are: ",
            "message_2": "The result is: ",
        },
        "inputs": {
            "to_print_1": ["RandInt", "list"],
            "to_print_2": ["MathList", "result"],
        },
    },
]

if __name__ == "__main__":
    Pipeline(pipeline_definition, 0).run()
