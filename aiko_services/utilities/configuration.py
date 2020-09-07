# To Do
# ~~~~~
# - Implement discovery for finding the default namespace
#   - Define a NameSpace class for holding information about a specific namespace

import os
import socket

__all__ = ["get_hostname", "get_namespace", "get_pid"]

DEFAULT_NAMESPACE="test"

def get_hostname():
    hostname = socket.gethostname()
    if hostname.find('.') < 0: hostname = socket.gethostbyaddr(hostname)[0]
    return hostname

def get_namespace():
    if "AIKO_NAMESPACE" in os.environ: return os.environ["AIKO_NAMESPACE"]
    return DEFAULT_NAMESPACE

def get_pid():
  return str(os.getpid())
