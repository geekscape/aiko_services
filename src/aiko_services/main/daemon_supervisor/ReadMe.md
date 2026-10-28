# Aiko Services main: the Daemon Supervisor

Start Aiko Services when the operating system starts.

The operating system starts **one** daemon for each host, the
[ProcessManager](../../../../documentation/concepts/process_manager.md), and
the ProcessManager definition file starts everything else: the broker, the
Registrar, Actors, Agents and Pipelines. So a `DaemonDefinition` describes one
daemon, not a fleet.

One `DaemonDefinition`, several renderers: a systemd unit on Linux, a launchd
agent on macOS. `choose_daemon_supervisor()` selects the one for this host, in
the way `choose_output()` selects a display backend. Windows gets
`UnsupportedDaemonSupervisorImpl`, which reports the platform instead of doing
something that cannot work.

`render` changes nothing, so you can read the service description before you
install it. `install` is the only command that changes the host.

Design record:
[ADR-026](../../../../constitution/adr/ADR-026_DaemonSupervision.md).

"Supervisor" rather than "Launcher": it starts, stops, installs, removes and
reports, which is more than launching, and "Launcher" reads as the macOS
`launchd` daemon. A daemon is the first thing to supervise, not necessarily
the only one.

## Install

```bash
pip install -e .          # "aiko_supervisor" is then on the PATH
aiko_supervisor --help
```

## Run

`aiko_supervisor.json` beside this ReadMe is an example definition file: it is
what `aiko01` runs. Render the service description for a host, which writes
nothing:

```bash
aiko_supervisor render --name aiko01 --user claude \
  --mqtt_host localhost --after network-online.target --after mosquitto.service \
  --executable /home/claude/venvs/venv_3.13/bin/aiko_process \
  /home/claude/aiko01_supervisor.json
```

Install it, which needs root on Linux, because the unit is written to
`/etc/systemd/system`:

```bash
sudo aiko_supervisor install --name aiko01 --user claude ... /home/claude/aiko01_supervisor.json
sudo systemctl start aiko01
```

Then `aiko_supervisor start | stop | status | uninstall --name aiko01`.

Two defaults are not obvious, and both come from a Raspberry Pi 5 deployment:

* `restart` is `always`, because the ProcessManager `--watchdog` option is
  recorded but nothing relaunches anything yet. The restarting belongs to the
  operating system for now.
* `PYTHONUNBUFFERED` is set, because Python buffers stdout when it is a pipe,
  which is what a service gets. Without it, the ProcessManager log stays in the
  buffer and the service looks silent.

Also note that **systemd's `PATH` does not include the virtual environment**.
Either give the definition file absolute pathnames, or set the `PATH` with
`--environment PATH=/home/claude/venvs/venv_3.13/bin:/usr/bin:/bin`. A command
that systemd cannot find fails with a `FileNotFoundError`, which the
ProcessManager logs as a warning only.

## Demonstration

These commands show the Daemon Supervisor and the ProcessManager definition
file operating on a real host. They are written for `aiko01`, a Raspberry Pi 5,
and run from a different computer. Replace the host name, the account and the
pathnames for your host.

### 1. The daemon runs, and nobody started it by hand

```bash
ssh claude@aiko01.local \
  'systemctl is-enabled aiko01; systemctl is-active aiko01; systemctl status aiko01 --no-pager | head -6'
```

`enabled` shows that it starts when the host starts. `active` shows that it is
running now.

### 2. Reach that Actor across the network

```bash
AIKO_MQTT_HOST=aiko01.local aiko_process list -n aiko01
```

This runs on your computer, in the virtual environment where you installed
Aiko Services, and speaks to the ProcessManager on the host. It shows Actor
discovery and a command, not only a retained topic:

```
Processes ...
  uid: 000000, pid: 1655, aiko_process run
  uid: 000001, pid: 1658, aiko_registrar
```

### 3. The "enabled" flag in the definition file

This starts a second ProcessManager, so the service of the host is not
touched. The definition has one enabled entry, one disabled entry, and one
entry with no flag:

An `ssh` command does not activate a virtual environment, so give
`aiko_process` its full pathname:

```bash
ssh claude@aiko01.local 'mkdir -p ~/demo && cd ~/demo && \
  printf "[\n  \"true  sleep 300\",\n  \"false sleep 400\",\n  \"sleep 500\"\n]\n" > demo.json && \
  PYTHONUNBUFFERED=1 AIKO_MQTT_HOST=localhost \
  ~/venvs/venv_3.13/bin/aiko_process run -n demo --unsafe demo.json'
```

`--unsafe` is here only so that the demonstration stops itself with
`aiko_process exit`, which travels on the message bus. A ProcessManager
runs `--safe` by default, and denies `exit`. See the ProcessManager
concept document.

The log shows what happened to each entry:

```
INFO  DEMO Create: <000001> ['sleep', '300']
INFO  DEMO Disabled: sleep 400
ERROR DEMO Definition entry must start with "true" or "false", skipped: sleep 500
```

From a second terminal, `pgrep -af "sleep 300|sleep 400|sleep 500"` shows that
only `sleep 300` runs. Stop the demonstration with
`~/venvs/venv_3.13/bin/aiko_process exit -n demo -gt 0`.

`PYTHONUNBUFFERED=1` is necessary when the output goes to a file or a pipe,
for the same reason the installed service sets it.

### 4. One definition, two platforms

```bash
aiko_supervisor render --platform systemd --name aiko01 --user claude \
  --mqtt_host localhost --after network-online.target --after mosquitto.service \
  --executable /home/claude/venvs/venv_3.13/bin/aiko_process \
  /home/claude/aiko01_supervisor.json

aiko_supervisor render --platform launchd --name aiko01 \
  --mqtt_host localhost /home/claude/aiko01_supervisor.json
```

The same `DaemonDefinition` becomes a systemd unit and a launchd property
list. Neither command writes anything.

### 5. The definition refuses what cannot work

```bash
python3 -c "
from aiko_services.main.daemon_supervisor import DaemonDefinition, choose_daemon_supervisor
for call, label in [
    (lambda: DaemonDefinition(name='aiko01', stop_timeout_seconds=5), 'stop timeout'),
    (lambda: DaemonDefinition(name='aiko01', restart='sometimes'), 'restart policy'),
    (lambda: choose_daemon_supervisor('upstart'), 'platform')]:
    try: call(); print(label, 'NO ERROR')
    except Exception as error: print(f'{label}: {error}')"
```

The stop timeout rule matters most. The operating system must wait longer than
the ProcessManager waits for its own processes. If it does not, the operating
system kills the ProcessManager while its processes are still stopping, which
leaves them running and makes a clean shutdown impossible.

### 6. The tests

```bash
pip install -e ".[test]"
pytest -q src/aiko_services/tests/unit/test_daemon_supervisor.py \
          src/aiko_services/tests/unit/test_process_manager.py
```

Expect `32 passed`. No broker is necessary: `render` and the parsing functions
are tested on their own.

### 7. Restart the host and walk away

```bash
ssh claude@aiko01.local 'sync; sudo sh -c "
  echo s > /proc/sysrq-trigger; sleep 1
  echo u > /proc/sysrq-trigger; sleep 1
  echo b > /proc/sysrq-trigger"'
sleep 90
ssh claude@aiko01.local 'uptime -s; systemctl is-active aiko01; pgrep -af bin/aiko_registrar'
```

The host restarts, and the service starts the ProcessManager, which starts the
Registrar, with no help. This uses SysRq because a clean `systemctl reboot` has
stalled on this host, which is not yet understood.

## Tests

```bash
pytest -q src/aiko_services/tests/unit/test_daemon_supervisor.py
```

`render` and `pathname` are pure functions, so they are tested directly.
`install`, `start`, `stop` and `status` change the host or run a platform
command, so they are exercised by the demonstration above, not by the tests.

## Files

| File | Contents |
|---|---|
| `daemon_supervisor.py` | `DaemonDefinition`, the `DaemonSupervisor` Interface, `UnsupportedDaemonSupervisorImpl` and `choose_daemon_supervisor()` |
| `systemd.py` | `SystemdDaemonSupervisorImpl`: a unit in `/etc/systemd/system` |
| `launchd.py` | `LaunchdDaemonSupervisorImpl`: a user agent in `~/Library/LaunchAgents` |
| `cli.py` | The `aiko_supervisor` command |
| `aiko_supervisor.json` | An example ProcessManager definition file |
