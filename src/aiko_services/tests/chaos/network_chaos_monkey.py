#!/usr/bin/env python3
#
# https://en.wikipedia.org/wiki/Chaos_engineering#Chaos_Monkey
#
# TCP reachability chaos monkey with modes
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Up:   Proxy frontend → backend
# Down: hardfail:       Frontend port closed (connection refused/reset)
# Down: blackhole:      Frontend accepts but never forwards (timeout)
# Down: drop_midstream: Proxy forwards but randomly kills sessions mid-flow
#
# "Backend":  TCP/IP port that the server is listening to
# "Frontend": TCP/IP port that can be controlled for chaos monkey testing
#
# Usage
# ~~~~~
# ./network_chaos_monkey.py status
# ./network_chaos_monkey.py up --backend_port 1883 --frontend_port 9883  \
#                             [--no_precheck]
#
# ./network_chaos_monkey.py down   --mode hardfail
#
# ./network_chaos_monkey.py toggle --mode hardfail --on 10 --off 10  \
#                                  --backend_port 1883 --frontend_port 9883
#
# ./network_chaos_monkey.py toggle --mode drop_midstream  \
#         --on 8 --off 5    --cycles 4 --jitter 2         \
#         --drop_chance 0.3 --drop_min_delay 2 --drop_max_delay 12
#
# ./network_chaos_monkey.py stop
#
# mosquitto_sub -h 127.0.0.1 -p 9883 -t test -V mqttv311 -v -d

import argparse
import asyncio
from contextlib import suppress
import os
import random
import signal
import socket
import subprocess
import sys
import time
from typing import Optional, Set

PIDFILE = "network_chaos_monkey.pid"
MODEFILE = "network_chaos_monkey.mode"   # "proxy", "sink", or "drop_midstream"

ACTIVE_CONNECTIONS: Set[asyncio.StreamWriter] = set()

# -------------
# Async servers
# -------------

async def _pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter):
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass
    finally:
        with suppress(Exception):
            dst.close()

async def _handle_proxy_client(
    cli_reader, cli_writer, backend_host, backend_port,
    drop_midstream=False, drop_chance=0.2,
    drop_min_delay=1.0, drop_max_delay=5.0):

    peer = None
    try:
        peer = cli_writer.get_extra_info("peername")
        print(f"[proxy] client connected: {peer}", flush=True)
        be_reader, be_writer = await asyncio.open_connection(
            backend_host, backend_port)
    except Exception as e:
        # Explicit message so it's obvious in logs what happened.
        print(f"[proxy] backend connect failed for client {peer}: {backend_host}:{backend_port} -> {e}", flush=True)
        try:
            cli_writer.close()
        except Exception:
            pass
        return

    if drop_midstream:
        ACTIVE_CONNECTIONS.add(cli_writer)

        async def killer():
            mn = max(0.0, float(min(drop_min_delay, drop_max_delay)))
            mx = max(0.0, float(max(drop_min_delay, drop_max_delay)))
            delay = random.uniform(mn, mx)
            await asyncio.sleep(delay)
            if random.random() < max(0.0, min(1.0, float(drop_chance))) and not cli_writer.is_closing():
                print(f"[drop_midstream] killing session {peer} after {delay:.2f}s", flush=True)
                try:
                    cli_writer.close()
                except Exception:
                    pass
                try:
                    be_writer.close()
                except Exception:
                    pass

        asyncio.create_task(killer())

    t1 = asyncio.create_task(_pump(cli_reader, be_writer))   # client -> backend
    t2 = asyncio.create_task(_pump(be_reader, cli_writer))   # backend -> client
    await asyncio.gather(t1, t2)

    if drop_midstream:
        ACTIVE_CONNECTIONS.discard(cli_writer)

async def _run_proxy(
    front_host, front_port, backend_host, backend_port,
    drop_midstream=False, drop_chance=0.2,
    drop_min_delay=1.0, drop_max_delay=5.0):

    server = await asyncio.start_server(
        lambda r, w: _handle_proxy_client(
            r, w, backend_host, backend_port,
            drop_midstream, drop_chance, drop_min_delay, drop_max_delay),
            front_host, front_port
    )
    tag = "[proxy+drop_midstream]" if drop_midstream else "[proxy]"
    print(f"{tag} UP: {front_host}:{front_port} → {backend_host}:{backend_port}", flush=True)
    async with server:
        await server.serve_forever()

async def _handle_sink_client(cli_reader, cli_writer):
    try:
        while True:
            data = await cli_reader.read(65536)
            if not data:
                break
            # discard; never respond
    except Exception:
        pass
    finally:
        try:
            cli_writer.close()
        except Exception:
            pass

async def _run_sink(front_host, front_port):
    server = await asyncio.start_server(
        _handle_sink_client, front_host, front_port)
    print(f"[sink] DOWN (blackhole): {front_host}:{front_port}", flush=True)
    async with server:
        await server.serve_forever()

# ------------
# Daemon entry
# ------------

def _serve_entry(args):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if args.behavior == "proxy":
            coro = _run_proxy(args.host, args.frontend_port,
                              args.backend_host, args.backend_port,
                              drop_midstream=False)
        elif args.behavior == "sink":
            coro = _run_sink(args.host, args.frontend_port)
        elif args.behavior == "drop_midstream":
            coro = _run_proxy(args.host, args.frontend_port,
                              args.backend_host, args.backend_port,
                              drop_midstream=True,
                              drop_chance=args.drop_chance,
                              drop_min_delay=args.drop_min_delay,
                              drop_max_delay=args.drop_max_delay)
        else:
            print(f"Unknown behavior: {args.behavior}", file=sys.stderr)
            sys.exit(2)
        loop.run_until_complete(coro)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            loop.close()
        except Exception:
            pass

# ---------------
# Process helpers
# ---------------

def _read_pid() -> Optional[int]:
    try:
        with open(PIDFILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None

def _write_pid(pid: int):
    with open(PIDFILE, "w") as f:
        f.write(str(pid))

def _write_modefile(behavior: str):
    with open(MODEFILE, "w") as f:
        f.write(behavior)

def _read_modefile() -> Optional[str]:
    try:
        with open(MODEFILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None

def _is_running(pid: Optional[int]) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _kill_pid(pid: Optional[int]):
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        if sys.platform.startswith("win"):
            try:
                os.kill(pid, signal.SIGBREAK)
            except Exception:
                pass

def _spawn_detached(argv_for_child) -> int:
    kwargs = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    elif os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(argv_for_child,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL,
                            **kwargs)
    return proc.pid

def _precheck_backend(host: str, port: int, timeout: float = 1.5) -> bool:
    """Synchronous reachability check to avoid 'UP' when backend is down."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        print(f"[precheck] backend {host}:{port} unreachable: {e}", file=sys.stderr)
        return False

# --------
# Commands
# --------

def cmd_up(args):
    pid = _read_pid()
    if _is_running(pid):
        print(f"Already UP (PID {pid})")
        return

    behavior = "proxy"
    if args.mode == "drop_midstream":
        behavior = "drop_midstream"

    if args.precheck and not _precheck_backend(args.backend_host, args.backend_port, args.precheck_timeout):
        # Fail fast so the mapping is truly symmetric & predictable.
        sys.exit(1)

    serve_argv = [sys.executable, __file__, "serve",
                  "--behavior", behavior,
                  "--host", args.host,
                  "--frontend_port", str(args.frontend_port),
                  "--backend_host", args.backend_host,
                  "--backend_port", str(args.backend_port),
                  "--drop_chance", str(args.drop_chance),
                  "--drop_min_delay", str(args.drop_min_delay),
                  "--drop_max_delay", str(args.drop_max_delay)]
    child_pid = _spawn_detached(serve_argv)
    _write_pid(child_pid)
    _write_modefile(behavior)
    print(f"UP: {behavior} {args.host}:{args.frontend_port} → {args.backend_host}:{args.backend_port} (PID {child_pid})")

def cmd_down(args):
    mode = args.mode
    pid = _read_pid()

    if mode == "hardfail":
        if _is_running(pid):
            _kill_pid(pid)
            time.sleep(0.2)
        for f in (PIDFILE, MODEFILE):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        print("DOWN: hardfail (port closed).")

    elif mode == "blackhole":
        if _is_running(pid):
            _kill_pid(pid)
            time.sleep(0.2)
        serve_argv = [sys.executable, __file__, "serve",
                      "--behavior", "sink",
                      "--host", args.host,
                      "--frontend_port", str(args.frontend_port)]
        child_pid = _spawn_detached(serve_argv)
        _write_pid(child_pid)
        _write_modefile("sink")
        print(f"DOWN: blackhole at {args.host}:{args.frontend_port} (PID {child_pid})")

    elif mode == "drop_midstream":
        if _is_running(pid):
            _kill_pid(pid)
            time.sleep(0.2)
        serve_argv = [sys.executable, __file__, "serve",
                      "--behavior", "drop_midstream",
                      "--host", args.host,
                      "--frontend_port", str(args.frontend_port),
                      "--backend_host", args.backend_host,
                      "--backend_port", str(args.backend_port),
                      "--drop_chance", str(args.drop_chance),
                      "--drop_min_delay", str(args.drop_min_delay),
                      "--drop_max_delay", str(args.drop_max_delay)]
        child_pid = _spawn_detached(serve_argv)
        _write_pid(child_pid)
        _write_modefile("drop_midstream")
        print(f"DOWN: drop_midstream at {args.host}:{args.frontend_port} (PID {child_pid})")

def cmd_status(_args):
    pid = _read_pid()
    if _is_running(pid):
        beh = _read_modefile() or "unknown"
        print(f"Status: running ({beh}) PID {pid}")
    else:
        print("Status: DOWN (no process)")

def cmd_stop(_args):
    pid = _read_pid()
    if not _is_running(pid):
        print("Nothing to stop (no running process).")
        for f in (PIDFILE, MODEFILE):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        return

    print(f"Stopping chaos monkey (PID {pid}) ...")
    _kill_pid(pid)
    time.sleep(0.2)

    for f in (PIDFILE, MODEFILE):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
    print("Stopped.")

def _jittered(base: float, jitter: float) -> float:
    if jitter <= 0:
        return max(base, 0.1)
    delta = random.uniform(-jitter, +jitter)
    return max(base + delta, 0.1)

def cmd_toggle(args):
    if args.seed is not None:
        random.seed(args.seed)

    j_on  = args.jitter_on  if args.jitter_on  is not None else args.jitter
    j_off = args.jitter_off if args.jitter_off is not None else args.jitter

    for i in range(1, args.cycles + 1):
        on_dur  = _jittered(args.on,  j_on)
        off_dur = _jittered(args.off, j_off)

        print(f"[cycle {i}] UP for {on_dur:.2f}s")
        cmd_up(args)
        time.sleep(on_dur)

        print(f"[cycle {i}] DOWN for {off_dur:.2f}s (mode={args.mode})")
        cmd_down(args)
        time.sleep(off_dur)

# ----------
# CLI parser
# ----------

def parse_args():
    p = argparse.ArgumentParser(description="Network Chaos Monkey (proxy + hardfail/blackhole/drop_midstream)")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default="0.0.0.0", help="Frontend bind address")
    common.add_argument("--frontend_port", type=int, default=1883, help="Frontend port for tcp_client connections")
    common.add_argument("--backend_host", default="127.0.0.1", help="Backend server host (when proxying)")
    common.add_argument("--backend_port", type=int, default=9883, help="Backend server port (when proxying)")
    # drop_midstream tuning (safe to pass always; ignored unless behavior == drop_midstream)
    common.add_argument("--drop_chance", type=float, default=0.2, help="Probability [0..1] to kill a session")
    common.add_argument("--drop_min_delay", type=float, default=1.0, help="Earliest kill (seconds)")
    common.add_argument("--drop_max_delay", type=float, default=5.0, help="Latest kill (seconds)")
    # precheck toggle
    common.add_argument("--no_precheck", dest="precheck", action="store_false",
                        help="Do not verify backend reachability before UP")
    common.add_argument("--precheck", dest="precheck", action="store_true",
                        help=argparse.SUPPRESS)
    common.add_argument("--precheck_timeout", type=float, default=1.5, help="Backend precheck timeout (seconds)")
    common.set_defaults(precheck=True)

    up = sub.add_parser("up", parents=[common], help="Start UP state (proxy or drop_midstream)")
    up.add_argument("--mode", choices=["hardfail", "blackhole", "drop_midstream"], default="hardfail",
                    help="UP behavior: proxy (hardfail), or proxy with drop_midstream")
    up.set_defaults(func=cmd_up)

    down = sub.add_parser("down", parents=[common], help="Enter DOWN state")
    down.add_argument("--mode", choices=["hardfail", "blackhole", "drop_midstream"], required=True,
                      help="DOWN behavior")
    down.set_defaults(func=cmd_down)

    status = sub.add_parser("status", help="Show current status")
    status.set_defaults(func=cmd_status)

    stop = sub.add_parser("stop", help="Stop any running chaos monkey process")
    stop.set_defaults(func=cmd_stop)

    toggle = sub.add_parser("toggle", parents=[common], help="Alternate UP/DOWN cycles")
    toggle.add_argument("--mode", choices=["hardfail", "blackhole", "drop_midstream"], required=True,
                        help="DOWN behavior during toggling")
    toggle.add_argument("--on", type=float, default=5.0, help="Seconds UP")
    toggle.add_argument("--off", type=float, default=5.0, help="Seconds DOWN")
    toggle.add_argument("--cycles", type=int, default=5, help="Number of cycles")
    toggle.add_argument("--jitter", type=float, default=0.0, help="±seconds jitter applied to both on/off")
    toggle.add_argument("--jitter_on", type=float, default=None, help="Override jitter for UP")
    toggle.add_argument("--jitter_off", type=float, default=None, help="Override jitter for DOWN")
    toggle.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    toggle.set_defaults(func=cmd_toggle)

    serve = sub.add_parser("serve", help=argparse.SUPPRESS)
    serve.add_argument("--behavior", choices=["proxy", "sink", "drop_midstream"], required=True)
    serve.add_argument("--host", required=True)
    serve.add_argument("--frontend_port", type=int, required=True)
    serve.add_argument("--backend_host", default="127.0.0.1")
    serve.add_argument("--backend_port", type=int, default=9883)
    serve.add_argument("--drop_chance", type=float, default=0.2)
    serve.add_argument("--drop_min_delay", type=float, default=1.0)
    serve.add_argument("--drop_max_delay", type=float, default=5.0)
    serve.set_defaults(func=lambda a: _serve_entry(a))

    return p.parse_args()

def main():
    args = parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
