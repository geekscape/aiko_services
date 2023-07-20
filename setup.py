import os
import re
from setuptools import find_packages, setup

re_version = re.compile(r".*__version__ = [\'\"](.*?)[\'\"]", re.S)
base_path = os.path.dirname(__file__)
base_package = "aiko_services"

init_path = os.path.join(base_path, base_package, "__init__.py")
with open(init_path, "r") as init_file:
    module_content = init_file.read()
    match = re_version.match(module_content)
    if match:
        version = match.group(1)
    else:
        raise RuntimeError("Cannot find __version__ in {}".format(init_path))

setup(
    name="aiko-services",
    version=version,
    description="Asynchronous message service framework",
    author="Andy Gelme",
    author_email="geekscape@gmail.com",
    packages=find_packages(),
    install_requires=[
        "asciimatics>=1.14.0",
        "avro>=1.11.1",
        "avro-validator>=1.2.1",
        "click>=8.0",
        "networkx<=2.8",
        "numpy>=1.19.1",
        "paho-mqtt>=1.6.1",
        "Pillow>=9.0.0",
        "pyyaml>=5.3.1",
        "requests>=2.25.1",
        "transitions>=0.8.10",
        "wrapt>=1.12.1",
        "xerox>=0.4.1"
    ],
    entry_points={
        "console_scripts": [
            "aiko = aiko_services.cli:main",
            "aiko_dashboard = aiko_services.dashboard:main",
            "aiko_registrar = aiko_services.registrar:main"
        ]
    }
)
