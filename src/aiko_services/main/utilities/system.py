#!/usr/bin/env python3
#
# To Do
# ~~~~~
# - None, yet !

from datetime import timedelta
import gc
import platform
import psutil
import subprocess

__all__ = [
    "dir_base_name",
    "get_memory_used", "get_virtual_memory",
    "print_memory_used", "print_virtual_memory",
    "get_uptime"
]

DEFAULT_MEMORY_UNIT = "Mb"
DEFAULT_VIRTUAL_MEMORY_UNIT = "Gb"

# --------------------------------------------------------------------------- #
# Like "dirname" and "basename" combined, used by "../main/hyperspace.py"

def dir_base_name(path: str) -> tuple[str, str]:
    if path is None or path == "":
        return (".", "")
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    index = path.rfind("/")
    if index == -1:
        return (".", path)
    if index == 0:
        return ("/", path[1:])
    return (path[:index], path[index+1:])

# --------------------------------------------------------------------------- #

def _get_scale(unit):
    if unit.lower() == "kb":
        scale = 2 ** 10  # binary KiloByte = 1,024 bytes
        unit = "Kbyte"
    elif unit.lower() == "mb":
        scale = 2 ** 20  # binary MegaByte = 1,048,576 bytes
        unit = "Mbyte"
    elif unit.lower() == "gb":
        scale = 2 ** 30  # binary GigaByte = 1,073,741,824 bytes
        unit = "Gbyte"
    elif unit.lower() == "tb":
        scale = 2 ** 40  # binary TeraByte = 1,099,511,627,776 bytes
        unit = "Tbyte"
    else:
        raise ValueError(f"Unknown unit: {unit}")
    return scale, unit

# --------------------------------------------------------------------------- #

def get_memory_used(unit=DEFAULT_MEMORY_UNIT):
    gc.collect()
    scale, unit = _get_scale(unit)
    memory_info =  psutil.Process().memory_info()
    memory_rss_used = memory_info.rss / scale
    memory_vms_used = memory_info.vms / scale
    return memory_rss_used, memory_vms_used, unit

def print_memory_used(label, unit=DEFAULT_MEMORY_UNIT):
    memory_rss_used, memory_vms_used, unit =  get_memory_used(unit)
    rss_used = f"used: {memory_rss_used:0.3f} {unit}"
    vms_used = f"used: {memory_vms_used:0.3f} {unit}"
    print(f"{label}Memory RSS {rss_used}, VMS {vms_used}")

def get_virtual_memory(unit=DEFAULT_VIRTUAL_MEMORY_UNIT):
    gc.collect()
    scale, unit = _get_scale(unit)
    virtual_memory_available = psutil.virtual_memory().available / scale
    virtual_memory_used = psutil.virtual_memory().used / scale
    return virtual_memory_available, virtual_memory_used, unit

def print_virtual_memory(label, unit=DEFAULT_VIRTUAL_MEMORY_UNIT):
    virtual_memory_available, virtual_memory_used, unit =  \
        get_virtual_memory(unit)
    used = f"used: {virtual_memory_used:0.3f} {unit}"
    available = f"available: {virtual_memory_available:0.3f} {unit}"
    print(f"{label}Virtual Memory {used}, {available}")

# --------------------------------------------------------------------------- #

def get_uptime():
    try:
        os_name = platform.system()

        if os_name == "Linux":
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.readline().split()[0])

        elif os_name == "Darwin":  # Mac OS X
            output = subprocess.check_output(
                ["sysctl", "-n", "kern.boottime"]).decode()
            boot_time_str = output.split("}")[0].split("{")[1].split(",")
            boot_time_seconds = int(boot_time_str[0].split("=")[1])
            uptime_seconds = int(subprocess.check_output(
                ["date", "+%s"]).decode()) - boot_time_seconds

        elif os_name == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            uptime_ms = kernel32.GetTickCount64()
            uptime_seconds = uptime_ms // 1000

        else:
            raise RuntimeError(
                f"get_uptime(): Operating System unsupported: {os_name}")

        return str(timedelta(seconds=uptime_seconds))

    except Exception as exception:
        return f"Error: {exception}"

# --------------------------------------------------------------------------- #

def main():
    print("System uptime:", get_uptime())
    print_memory_used("")
    print_virtual_memory("")

if __name__ == "__main__":
    main()
