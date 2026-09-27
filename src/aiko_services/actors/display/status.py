#!/usr/bin/env python3
#
# Aiko Services: OLED status screens
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The "status" applet: the main purpose of the Actor, a display for a
# headless host.  Two screens, each as text or as a chart of its values
# over the last 128 samples (one per refresh):
#
#   screen=host   IP address, CPU and memory, disk and network, the load
#                 averages, temperature with the fan and CPU speed, uptime,
#                 the newest (log ...) line
#                 view=cpu_mem   CPU (solid) and memory (dotted), 0..100%
#                 view=rx_tx     received (solid) and sent (dotted) bytes/s
#   screen=wifi   SSID, channel, band and bandwidth, RSSI and link quality,
#                 the bit rates, the access point, the interface's traffic
#                 view=rssi      RSSI in dBm, -90..-30
#                 view=rx_tx     the Wi-Fi interface's bytes/s
#
# Options: rate=N updates per second (1), date=on adds the date, screen=,
# view=.  The console's "s" steps through the screens and "S" through the
# views of the current screen (keys.py).
#
# Readings and their cost on the event-loop thread (P2): psutil calls are
# non-blocking; /proc/net/wireless is a file read; the fan is
# "pinctrl get 14" (about 3 ms, every 2 s); the Wi-Fi details are
# "iw dev IF link" and "iw dev IF info" (about 6 ms together, every 10 s,
# only while the Wi-Fi text screen shows), else one "nmcli" call (about
# 50 ms).  Tools are looked for in /usr/sbin and /sbin too, which a
# non-login shell's PATH can lack.  Without Linux, iw or NetworkManager, or
# a wireless interface, the rows say so.
# History (P9): 128 samples per value, module level, kept while the process
# lives, so that switching views keeps the chart.
#
# Not part of the Interface composition pattern (ADR-022 category
# Presentation and CLI shells) — see e_10 §2.16: plain
# presentation classes owned by the Actor.

import collections
from datetime import datetime
import fcntl
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time

from PIL import ImageDraw

from aiko_services.examples.oled.applets import (
    APPLETS, Applet, ip_address, on_off, per_second,
)
from aiko_services.examples.oled.graphics import INK, Font, stamp

__all__ = ["HISTORY", "STATUS_SCREENS", "STATUS_VIEWS", "StatusApplet",
           "fan_state", "parse_iw", "parse_nmcli", "parse_wireless",
           "wifi_details", "wifi_signal"]

STATUS_SCREENS = ("host", "wifi")
STATUS_VIEWS = {"host": ("text", "cpu_mem", "rx_tx"),
                "wifi": ("text", "rssi", "rx_tx")}
HISTORY_LENGTH = 256                   # samples: one per column, hosts to 256 wide
HISTORY = {name: collections.deque(maxlen=HISTORY_LENGTH)
           for name in ("cpu", "mem", "rx", "tx", "rssi", "wrx", "wtx")}
FAN_GPIO = 14
FAN_PERIOD = 2.0                       # seconds between fan readings
WIFI_DETAILS_PERIOD = 10.0             # seconds between nmcli calls
RSSI_RANGE = (-90, -30)                # dBm, the fixed chart scale
_CHART_FONT = Font("5x7")              # charts keep their fixed layout

# Readings ----------------------------------------------------------------- #

def _tool(name):
    """The path of a command, looking in /usr/sbin and /sbin as well as
    PATH (a non-login shell often lacks them); None when absent"""

    found = shutil.which(name)
    if found:
        return found
    for path in (f"/usr/sbin/{name}", f"/sbin/{name}"):
        if os.access(path, os.X_OK):
            return path
    return None

def _run(command, timeout):
    """The command's output, or "" when it fails or times out"""

    try:
        return subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""

def _band(mhz):
    return "2.4GHz" if mhz < 3000 else "5GHz" if mhz < 5925 else "6GHz"

def fan_state():
    """The level of the fan's GPIO line: "1" high, "0" low, "-" unknown
    ("pinctrl" on a Raspberry Pi, else "gpioget")"""

    pinctrl, gpioget = _tool("pinctrl"), _tool("gpioget")
    if pinctrl:
        match = re.search(r"\|\s*(hi|lo)\b", _run([pinctrl, "get", str(FAN_GPIO)], 0.5))
        if match:
            return "1" if match.group(1) == "hi" else "0"
    elif gpioget:
        out = _run([gpioget, "-c", "gpiochip0", str(FAN_GPIO)], 0.5).strip()
        if "inactive" in out or out.endswith("0"):
            return "0"
        if "active" in out or out.endswith("1"):
            return "1"
    return "-"

def parse_wireless(text):
    """(interface, link quality, level dBm) of the strongest interface in
    /proc/net/wireless, or None"""

    best = None
    for line in text.splitlines()[2:]:
        fields = line.replace(":", " ").split()
        if len(fields) < 4:
            continue
        try:
            quality, level = float(fields[2]), float(fields[3])
        except ValueError:
            continue
        if best is None or quality > best[1]:
            best = (fields[0], int(quality), int(level))
    return best

def wifi_signal():
    """(interface, link quality, RSSI dBm) from /proc/net/wireless (Linux),
    or None without a wireless interface"""

    try:
        with open("/proc/net/wireless") as wireless:
            return parse_wireless(wireless.read())
    except OSError:
        return None

_NMCLI_FIELDS = ("ACTIVE", "DEVICE", "SSID", "BSSID", "CHAN", "FREQ", "RATE",
                 "SIGNAL", "BANDWIDTH")

def parse_nmcli(text, interface):
    """The active access point of the interface from "nmcli -t -e yes -f
    ACTIVE,DEVICE,SSID,BSSID,CHAN,FREQ,RATE,SIGNAL,BANDWIDTH dev wifi list":
    a dict with ssid, bssid, channel, mhz, band, rate, signal, bandwidth"""

    for line in text.splitlines():
        fields = [field.replace("\\:", ":").replace("\\\\", "\\")
                  for field in re.split(r"(?<!\\):", line)]
        if len(fields) < len(_NMCLI_FIELDS) or fields[0] != "yes" or fields[1] != interface:
            continue
        details = dict(zip((name.lower() for name in _NMCLI_FIELDS), fields))
        mhz = int(details.pop("freq").split()[0] or 0)
        return {
            "ssid": details["ssid"], "bssid": details["bssid"].lower(),
            "channel": details["chan"], "mhz": mhz, "band": _band(mhz),
            "rate": details["rate"].replace(" Mbit/s", "Mb/s"),
            "signal": details["signal"],
            "bandwidth": details["bandwidth"].replace(" MHz", "MHz"),
        }
    return {}

def parse_iw(link_text, info_text=""):
    """The link from "iw dev IF link" and "iw dev IF info": ssid, bssid,
    mhz, band, channel, bandwidth, tx_rate and rx_rate (Mbit/s) and
    signal_dbm, as far as the outputs give them; {} when not connected"""

    details = {}
    match = re.search(r"Connected to ([0-9A-Fa-f:]{17})", link_text)
    if match:
        details["bssid"] = match.group(1).lower()
    match = re.search(r"^\s*SSID:\s*(.+?)\s*$", link_text, re.M)  \
        or re.search(r"^\s*ssid (.+?)\s*$", info_text, re.M)
    if match:
        details["ssid"] = match.group(1)
    match = re.search(r"^\s*freq:\s*([\d.]+)", link_text, re.M)
    if match:
        details["mhz"] = int(float(match.group(1)))
    match = re.search(r"^\s*signal:\s*(-?\d+)", link_text, re.M)
    if match:
        details["signal_dbm"] = int(match.group(1))
    for which in ("tx", "rx"):
        match = re.search(rf"^\s*{which} bitrate:\s*([\d.]+)\s*MBit/s", link_text, re.M)
        if match:
            details[f"{which}_rate"] = float(match.group(1))
    match = re.search(r"channel (\d+) \((\d+) MHz\), width: (\d+) MHz", info_text)
    if match:
        details["channel"] = match.group(1)
        details.setdefault("mhz", int(match.group(2)))
        details["bandwidth"] = f"{match.group(3)}MHz"
    if "mhz" in details:
        details["band"] = _band(details["mhz"])
    return details if "bssid" in details else {}

def _essid(interface):
    """The SSID through the wireless-extensions ioctl: the fallback without
    NetworkManager"""

    import ctypes
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        essid = ctypes.create_string_buffer(32)
        request = struct.pack("16sPHH", interface.encode(), ctypes.addressof(essid), 32, 0)
        try:
            fcntl.ioctl(sock.fileno(), 0x8B1B, request)     # SIOCGIWESSID
        except OSError:
            return ""
        return essid.value.decode(errors="replace")

def wifi_details(interface):
    """SSID, access point, channel, band, bandwidth and bit rates of the
    interface's link, from iw, else from NetworkManager (its rate and
    signal percent instead); only the SSID without either"""

    iw, nmcli = _tool("iw"), _tool("nmcli")
    if iw:
        details = parse_iw(_run([iw, "dev", interface, "link"], 1.0),
                           _run([iw, "dev", interface, "info"], 1.0))
        if details:
            return details
    if nmcli:
        details = parse_nmcli(_run(
            [nmcli, "-t", "-e", "yes", "-f", ",".join(_NMCLI_FIELDS),
             "dev", "wifi", "list", "--rescan", "no"], 2.0), interface)
        if details:
            return details
    try:
        return {"ssid": _essid(interface)} if sys.platform.startswith("linux") else {}
    except Exception:
        return {}

# The chart ---------------------------------------------------------------- #

def draw_chart(frame, top, series, low, high):
    """Plot the series from the row "top" to the bottom of the frame: the
    newest sample at the right, one column each; a solid trace joins the
    points, a dotted one plots every other column.  A baseline marks 0"""

    bottom = frame.height - 1
    span = max(bottom - top, 1)
    draw = ImageDraw.Draw(frame)
    draw.line((0, bottom, frame.width - 1, bottom), fill=INK)

    def y_of(value):
        fraction = (value - low) / (high - low) if high > low else 0.0
        return bottom - round(max(0.0, min(1.0, fraction)) * span)

    for values, style in series:
        values = list(values)[-frame.width:]   # the newest columns that fit
        points = [(frame.width - len(values) + i, y_of(value))
                  for i, value in enumerate(values)]
        if style == "dotted":
            for x, y in points:
                if x % 2 == 0:
                    frame.putpixel((x, y), INK)
        elif len(points) == 1:
            frame.putpixel(points[0], INK)
        else:
            draw.line(points, fill=INK)

def chart_heading(frame, top, legend, note=""):
    """The row above the chart: a sample of each trace with its name and
    current value, then a note (the scale) at the right"""

    font = _CHART_FONT
    x, mid = 0, top + 3
    draw = ImageDraw.Draw(frame)
    for text, style in legend:
        if style == "dotted":
            for dot in range(0, 6, 2):
                frame.putpixel((x + dot, mid), INK)
        else:
            draw.line((x, mid, x + 5, mid), fill=INK)
        x += 8
        ink = font.render_line(text)
        stamp(frame, ink, x, top)
        x += ink.width + 6
    if note:
        ink = font.render_line(note)
        stamp(frame, ink, min(x, frame.width - ink.width), top)

# The applet --------------------------------------------------------------- #

def _screen(text):
    if text not in STATUS_SCREENS:
        raise ValueError(text)
    return text

def _view(text):
    if not any(text in views for views in STATUS_VIEWS.values()):
        raise ValueError(text)
    return text

class StatusApplet(Applet):
    """The host's status ("screen=host", the default): IP address; CPU and
    memory; disk and network traffic; the 1, 5 and 15 minute load averages;
    temperature, the fan and the CPU speed (where the host has a sensor);
    uptime; the newest (log ...) line last.  Or the Wi-Fi link
    ("screen=wifi").  As text ("view=text") or as a chart of the screen's
    values over the last 128 refreshes ("view=cpu_mem", "rx_tx", "rssi").
    Refreshed "rate" times a second (once).  Numbers keep a fixed width so
    the text doesn't jump.  Without the title row the first line is the
    host name and the connection state, and the time precedes the uptime;
    "date=on" adds the date"""

    name = "status"
    fps = 1
    wants_title = True
    OPTIONS = {"rate": float, "date": on_off, "screen": _screen, "view": _view}
    description = "host_text"
    summary = ("The host's status, or the Wi-Fi link (screen=wifi), as text or a chart "
               "(view=cpu_mem|rx_tx|rssi): IP, CPU, memory, disk, network, load, "
               "temperature, fan, uptime, newest log line")

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.fps = max(0.1, min(10.0, self.options.get("rate", 1.0)))
        self.screen = self.options.get("screen", "host")
        self.view = self.options.get("view", "text")
        if self.view not in STATUS_VIEWS[self.screen]:
            raise ValueError(f"view={self.view} is not one of the {self.screen} views")
        self.description = f"{self.screen}_{self.view}"
        import psutil
        self.psutil = psutil
        psutil.cpu_percent(interval=None)  # starts the measurement
        self._fan = (0.0, "-")            # (read at, level)
        signal = wifi_signal()
        self._wifi = (0.0, signal[0] if signal else None, {})  # (read at, interface, details)
        self._before = (time.monotonic(), self._network_bytes())
        self._rates = (0.0, 0.0, 0.0, 0.0)  # rx, tx, wifi rx, wifi tx per second

    # Readings --------------------------------------------------------- #

    def _network_bytes(self):
        """(all interfaces but loopback, the Wi-Fi interface): (received,
        sent) bytes each"""

        counters = self.psutil.net_io_counters(pernic=True)
        wifi = self._wifi[1]
        total = [counter for name, counter in counters.items()
                 if not name.startswith("lo")]
        return ((sum(counter.bytes_recv for counter in total),
                 sum(counter.bytes_sent for counter in total)),
                ((counters[wifi].bytes_recv, counters[wifi].bytes_sent)
                 if wifi in counters else (0, 0)))

    def _cpu_speed(self):
        try:
            frequency = self.psutil.cpu_freq()
            return f"{frequency.current:.0f}MHz" if frequency else ""
        except (AttributeError, NotImplementedError, OSError, RuntimeError):
            return ""

    def _temperature(self):
        try:
            sensors = self.psutil.sensors_temperatures()  # Linux only
        except (AttributeError, NotImplementedError, OSError):
            return None
        for readings in sensors.values():
            if readings:
                return readings[0].current
        return None

    def _fan_state(self):
        now = time.monotonic()
        if now - self._fan[0] >= FAN_PERIOD:
            self._fan = (now, fan_state())
        return self._fan[1]

    def _wifi_link(self):
        """(interface, quality, RSSI) now, and the cached details"""

        signal = wifi_signal()
        interface = signal[0] if signal else None
        now = time.monotonic()
        if interface != self._wifi[1]:
            self._wifi = (0.0, interface, {})
        if self.screen == "wifi" and self.view == "text" and interface  \
                and now - self._wifi[0] >= WIFI_DETAILS_PERIOD:
            self._wifi = (now, interface, wifi_details(interface))
        return signal, self._wifi[2]

    def sample(self):
        """Take every reading once, and record the charted ones"""

        psutil = self.psutil
        signal, details = self._wifi_link()
        now = (time.monotonic(), self._network_bytes())
        seconds = max(now[0] - self._before[0], 1e-6)
        (rx, tx), (wrx, wtx) = (
            tuple((b - a) / seconds for a, b in zip(before, after))
            for before, after in zip(self._before[1], now[1]))
        self._before = now
        self._rates = (rx, tx, wrx, wtx)
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory().percent
        for name, value in (("cpu", cpu), ("mem", memory), ("rx", rx), ("tx", tx),
                            ("wrx", wrx), ("wtx", wtx)):
            HISTORY[name].append(value)
        HISTORY["rssi"].append(signal[2] if signal else RSSI_RANGE[0])
        return {"cpu": cpu, "mem": memory, "signal": signal, "details": details}

    # Rows ------------------------------------------------------------- #

    def host_lines(self, reading):
        psutil = self.psutil
        rx, tx, _, _ = self._rates
        up = int(time.time() - psutil.boot_time())
        days, hours, minutes = up // 86400, up // 3600 % 24, up // 60 % 60
        uptime = f"{days}d{hours:02d}h" if days else f"{hours}h{minutes:02d}m"
        clock = datetime.now()
        temperature = self._temperature()
        titled = bool(self.host.title_rows())
        columns = self.host.columns()
        lines = []
        if not titled:
            lines.append(f"{self.host.name} {self.host.connection()}"[:columns])
        lines.append(f"IP {ip_address()}")
        if self.options.get("date"):
            lines.append(f"{clock:%a %d %b %Y}")
        lines.append(f"CPU {reading['cpu']:2.0f}% Mem {reading['mem']:2.0f}%")
        lines.append(f"Dsk {psutil.disk_usage(os.path.expanduser('~')).percent:2.0f}% "
                     f"R {per_second(rx)} T {per_second(tx)}")
        try:
            lines.append("Load {:.2f} {:.2f} {:.2f}".format(*os.getloadavg()))  # 1, 5, 15 min
        except (AttributeError, OSError):
            pass
        if temperature is not None:
            lines.append(f"Temp {temperature:2.0f}C F {self._fan_state()} "
                         f"{self._cpu_speed()}".rstrip())
        lines.append(f"Up {uptime}" if titled else f"{clock:%H:%M:%S} up {uptime}")
        log_lines = self.host.log_lines()
        if log_lines:
            lines.append(log_lines[-1])  # the newest line only, last: dropped first
        return lines

    def wifi_lines(self, reading):
        signal, details = reading["signal"], reading["details"]
        titled = bool(self.host.title_rows())
        columns = self.host.columns()
        lines = []
        if not titled:
            lines.append(f"{self.host.name} {self.host.connection()}"[:columns])
        if signal is None:
            lines += ["Wi-Fi: none",
                      "no wireless interface" if sys.platform.startswith("linux")
                      else "(Linux only)"]
            return lines
        interface, quality, rssi = signal
        _, _, wrx, wtx = self._rates
        ssid = details.get("ssid") or "?"
        lines.append(f"SSID {ssid}"[:columns])
        if details.get("channel"):
            lines.append(f"Ch {details['channel']} {details['band']} "
                         f"BW {details['bandwidth'] or '-'}"[:columns])
        lines.append(f"RSSI {rssi:d}dBm Q {quality}/70"[:columns])
        if "tx_rate" in details:
            lines.append(f"Tx {details['tx_rate']:.0f} Rx {details.get('rx_rate', 0):.0f} Mb/s"[:columns])
        elif details.get("rate"):
            lines.append(f"Rate {details['rate']} Sig {details['signal']}%"[:columns])
        if details.get("bssid"):
            lines.append(f"AP {details['bssid']}"[:columns])
        lines.append(f"R {per_second(wrx)} T {per_second(wtx)}")
        lines.append(f"IF {interface}"[:columns])
        return lines

    # Frames ----------------------------------------------------------- #

    def chart_frame(self, reading):
        frame = self.frame()
        top = self.host.title_rows()
        rx, tx, wrx, wtx = self._rates
        if self.view == "cpu_mem":
            legend = [(f"CPU {reading['cpu']:2.0f}%", "solid"),
                      (f"Mem {reading['mem']:2.0f}%", "dotted")]
            series, low, high, note = [(HISTORY["cpu"], "solid"),
                                       (HISTORY["mem"], "dotted")], 0, 100, ""
        elif self.view == "rssi":
            signal = reading["signal"]
            rssi = signal[2] if signal else RSSI_RANGE[0]
            legend = [(f"RSSI {rssi:d}dBm", "solid")]
            series, (low, high) = [(HISTORY["rssi"], "solid")], RSSI_RANGE
            note = f"{low}/{high}"
        else:                                   # rx_tx: the host's, or the Wi-Fi's
            received, sent = (rx, tx) if self.screen == "host" else (wrx, wtx)
            names = ("rx", "tx") if self.screen == "host" else ("wrx", "wtx")
            legend = [(f"R {per_second(received)}", "solid"),
                      (f"T {per_second(sent)}", "dotted")]
            high = max(max(HISTORY[names[0]], default=0), max(HISTORY[names[1]], default=0), 1024)
            series, low, note = [(HISTORY[names[0]], "solid"),
                                 (HISTORY[names[1]], "dotted")], 0, f"^{per_second(high).strip()}"
        chart_heading(frame, top, legend, note)
        draw_chart(frame, top + _CHART_FONT.cell_height, series, low, high)
        return frame

    def step(self):
        reading = self.sample()
        if self.view != "text":
            return self.chart_frame(reading)
        lines = self.host_lines(reading) if self.screen == "host" else self.wifi_lines(reading)
        frame = self.write_lines(lines)
        if self.screen == "host" and self.host.log_lines():
            self.host.log_seen()
        return frame

APPLETS["status"] = StatusApplet
