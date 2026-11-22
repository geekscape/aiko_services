---
title: Provision a host to run Aiko Services 24 hours a day
description: The sequence that turns a new host — a cloud instance or a
  physical edge computer — into one that runs the ProcessManager, its
  Actors and an application, and the de-clone step a copy must not skip
type: how-to
audience: [project-lead, developers, ai-coding-agents]
status: work-in-progress
ste: adapted
source:
  - scripts/host_declone.sh
  - scripts/respawn.sh
  - src/aiko_services/main/daemon_supervisor/ReadMe.md
  - src/aiko_services/actors/power_manager/ReadMe.md
related: [../concepts/process_manager, ../concepts/dashboard_plugin]
last_updated: 2026-11-20
---

# Provision a host to run Aiko Services 24 hours a day

This is the order in which a host is built, and the reason for each step.
It is written from the hosts that run it, and each step names what proves
that it worked. The last section lists what a host is, as data, for a
port to a declarative system such as NixOS.

A deployment has its own names, addresses and keys. **None of them are in
this document**, because this repository is public. Keep them in a
private note beside it.

## What a host is

The same sequence builds every kind, with different answers at each
step. The kind decides which steps apply, not what order they come in.

| Kind | Example | Which steps |
|---|---|---|
| A developer's own computer | a laptop | 4 to 7, and usually no hardware |
| A home or office server | a small always-on machine | 1 to 8 |
| An edge single-board computer | a Raspberry Pi on a vehicle | **All of them.** This is the demanding case |
| A cloud instance | a virtual host at a provider | 1, 2, 5, 7, 8. There is no bus and no panel, and the identity step is the provider's |

The edge computer is the one this document is written from, because it
needs every step. A cloud instance skips the hardware and the power
manager. A laptop usually skips the service as well, and runs the
ProcessManager by hand.

**Two things are the same for every kind.** The host is its own machine,
with an identity nothing else has. And the ProcessManager is the one
thing the operating system starts: everything else is an entry in its
definition.

## Before the first boot

| | |
|---|---|
| Operating system | Raspberry Pi OS, 64-bit, Debian 13 (trixie) |
| Storage | A USB SSD, which is faster and lasts longer than a card |
| Account | One account for the application, and one for development |

A Raspberry Pi 5 that boots from USB needs `usb_max_current_enable=1` in
`/boot/firmware/config.txt`. On a Pi 4 that line is inert, and it does no
harm to leave it in a shared configuration.

## Build each host, do not copy one

Build each new host from this procedure, and pull the code from `master`
and from the application's main branch. Do not copy the storage of a
host that runs.

- A built host has the latest code, and no identity of another host.
- Each defect found during a build becomes a step in this document, so
  the next build does not find it again.
- A copy carries the old host's identity, keys, queue and local changes.
  Step 1 removes the identity. Nothing removes the rest.

A copy is correct in one case only: to reuse storage that already holds
a built host, for a new host name. Then step 1 is mandatory.

## 1. De-clone, before the host meets a network

**Do this first on any host copied from another host's storage.** A copy
carries the original's identity, and two hosts that share it cannot both
be on one network.

```bash
sudo scripts/host_declone.sh --show        # it changes nothing
sudo scripts/host_declone.sh --confirm
sudo reboot
```

Four things are per-host, and a copy keeps all four: `/etc/machine-id`,
the SSH host keys, `/var/lib/NetworkManager/secret_key`, and the D-Bus
machine id that usually links to the first. NetworkManager derives the
stable IPv6 interface identifier from the first and the third. So two
copies take the same address, mDNS conflicts, and the host names trade
places.

Sharing the SSH host keys is worse than inconvenient. Every copy answers
as the same host, so `known_hosts` cannot tell them apart, and a host
that was substituted for another raises no warning.

**Changing the hostname does not do this.** The hostname is what an
operator sees. These four are what the network sees.

*Proved by:* `--show` reports values that no other host has, and the
host answers to its own name while a sibling is also running.

## 2. The host's own names

- The hostname.
- The access point SSID, where the host serves one. Name it after the
  host, so that an operator beside the machine knows which one it is.
- The entry in whatever inventory records which host went where.

## 3. The hardware

For a host with the power management module and a panel:

```
/boot/firmware/config.txt   dtparam=i2c_arm=on
                            dtparam=i2c_arm_baudrate=400000
/etc/modules                i2c-dev
```

The account needs the `i2c`, `gpio`, `spi`, `dialout` and `video` groups.
Install `i2c-tools` for diagnosis.

*Proved by:* `i2cdetect -y 1` answers at each address the deployment
expects. For the module and panel used here: the panel, two current
monitors and a battery pack temperature sensor.

**`i2cdetect` is in `/usr/sbin`**, and a command sent over `ssh` without
a terminal gets a PATH with no `sbin` in it. The command then reports
`i2cdetect: command not found` on a host where the package is installed.
Give the absolute path, or ask for a login shell:

```bash
ssh <host> '/usr/sbin/i2cdetect -y -r 1'
ssh <host> 'bash -lc "i2cdetect -y -r 1"'
```

The same trap applies to every administration tool in `sbin`. Read
`dpkg -L i2c-tools` before you conclude that a package is missing.

**Use `-r` on a bus that devices are already using.** The default probe
writes, and a write to a panel at its own address can put rubbish on the
screen. `-r` reads instead.

A probe can also answer at addresses the deployment does not expect: an
add-on board can carry an unprogrammed ID EEPROM, which reads as all
`0xff`. Record what a host answers at, so that the next host can be
compared to it.

## 4. Aiko Services

```bash
git clone <this repository> ~/aiko_services
cd ~/aiko_services && git switch master
python3 -m venv --system-site-packages ~/venvs/venv_3.13
~/venvs/venv_3.13/bin/pip install -e "$HOME/aiko_services[server,video]"
```

Add the extra for each camera that the host uses: `depthai` for a
Luxonis camera, `ids_peak` for an IDS camera. The IDS camera also needs
the vendor's native SDK, which is a separate installation.

**`--system-site-packages` is necessary.** The hardware Actors import
packages that the operating system supplies: `smbus2`, `gpiozero`,
`spidev`, `lgpio` and `gi`. A virtual environment without the system
packages cannot find them.

**The `video` extra installs an OpenCV wheel that is necessary.** It
hides the system `python3-opencv`. On a Raspberry Pi 4 the system
OpenCV encodes H.264 in software, at 166 ms for each 1080p frame. The
wheel uses the hardware encoder.

Record the exact versions, so that the next host can be compared:

```bash
~/venvs/venv_3.13/bin/pip list --local --format=freeze > ~/pip_freeze.txt
```

**A host runs `master`.** A host left on a topic branch is a host nobody
can reason about. Before moving a host off a branch, check what that
branch holds that `master` does not:

```bash
git merge-base --is-ancestor HEAD origin/master && echo "nothing is lost"
```

Two packages are needed beyond the declared dependencies, and only on a
host that has the hardware:

| Package | Needed by |
|---|---|
| `luma.oled`, `luma.core` | the SSD1306 panel, through `actors/display/outputs.py` |

`actors/display/outputs.py` imports `luma` where it is used, so a host
without the panel does not need it. It is not a declared dependency, and
that is worth knowing before a panel fails to appear.

*Proved by:* `aiko_power_manager sample --device mock` prints a reading,
and `aiko_dashboard --help` prints its options.

## 5. The power manager

Three artifacts, all rendered rather than copied, so that each host
writes its own:

**One artifact at a time, and that is deliberate**: each is read before
it is written, and the grant names whose privilege it is rather than
guessing from the account that runs `sudo`.

```bash
aiko_power_manager render unit                   # each writes nothing
aiko_power_manager render hook
aiko_power_manager render grant --account <account>

# The shutdown directory is not on a stock installation.  "install hook"
# declines rather than making it, because a directory under /usr/lib is
# the distribution's to own.
#
# Give it a mode.  "mkdir" without one follows root's umask, and a
# directory that the Actor's account cannot search makes the hook read
# as missing, which puts the host into quiesce for a hook that is there
sudo install -d -m 755 /usr/lib/systemd/system-shutdown

sudo aiko_power_manager install unit
sudo aiko_power_manager install hook
sudo aiko_power_manager install grant --account <account>

# "install unit" writes the unit and says this, and does not do it: the
# hold asserts at the NEXT boot, and only once the unit is enabled
sudo systemctl daemon-reload
sudo systemctl enable aiko_power_hold

aiko_power_manager verify
```

`render grant` refuses without `--account`. Under `sudo` the invoking
account is root, and a grant that gave root the privilege would grant
nothing to the account that needs it.

- the unit asserts the power hold at boot and sounds `booted`
- the shutdown hook is the only thing that releases the hold
- the grant is two exact commands, with absolute paths and no wildcard

*Proved by:* `verify` reports all three present, `systemctl is-enabled
aiko_power_hold` reports enabled, and `pinctrl get 5` shows the hold
asserted after a reboot.

**The hook matters more than the other two.** It is the only thing that
releases the hold. A host without it keeps its own power on after it
stops, and the battery pack goes flat where nobody is watching.

## 6. The ProcessManager

One definition file for each host, named after the host, and one service:

```bash
aiko_supervisor render --name <host> --user <account> \
  --working_directory /home/<account> --mqtt_host localhost \
  --after network-online.target --after mosquitto.service \
  --environment "PATH=/home/<account>/venvs/venv_3.13/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  --executable /home/<account>/venvs/venv_3.13/bin/aiko_process \
  /home/<account>/<host>_supervisor.json
```

Then the same command with `install` in place of `render`, as root.

Two options are easy to leave out and both cost an hour to find.
**`--working_directory`**, because a definition entry with a relative
command resolves against it. **`--environment PATH=...`**, because
systemd's own `PATH` does not include the virtual environment. A command
it cannot find is logged as a warning, and nothing else.

Keep a variant of the definition for each mode the host runs in, and a
symbolic link that selects one. Every host of a deployment has the same
four variants:

| Variant | Entries that run | Use |
|---|---|---|
| `_none` | The Registrar, the power manager | **While a host is built**, and to stop the capture |
| `_forward` | ...and the Display, the link to the receiver, and the forwarder | Send the queue, and capture nothing |
| `_prod` | ...and the camera Pipeline | Production |
| `_local` | `_prod`, with a receiver on the host itself in place of the link | A bench or boot test of the full chain. Nothing goes to the production receiver |

`_local` fills the host's own storage, because the receiver keeps each
segment. Use it for a test, then select `_none` or `_prod`.

```bash
ln -sfn <host>_supervisor.json_none ~/<host>_supervisor.json
```

The ProcessManager does not start a process again when it exits (see
[ProcessManager](../concepts/process_manager.md)). So each entry that
must keep running wraps its command in `scripts/respawn.sh`:

```json
"command": ["/home/<account>/aiko_services/scripts/respawn.sh", "10",
            "/home/<account>/venvs/venv_3.13/bin/aiko_registrar"]
```

`respawn.sh` starts the command again 10 s after it exits. It sends
`SIGTERM` to the command when the ProcessManager stops the entry.

*Proved by:* `systemctl is-enabled` and `is-active`, then
`aiko_process list` shows the entries.

## 7. The application

The application's own repository, branch and configuration. A host that
cannot reach that repository cannot be completed. Give it the code before
this step, rather than during it.

### Give the host the history, not a key

Where the application repository is private, **a host that leaves the
building must not hold a key to it**. A key on a mobile host travels with
the host. A key that is lost without being noticed cannot be revoked for
one host alone.

Carry the history instead, from a computer that does have access:

```bash
# On the computer with the clone
git bundle create /tmp/application.bundle --all
scp /tmp/application.bundle <account>@<host>:~/

# On the host
git fetch ~/application.bundle "refs/heads/*:refs/remotes/source/*"
git checkout <commit>
```

A bundle is one file, and the far end needs no credential. The fetch
writes `source/*` remote-tracking refs. The host's own branch and its
`origin` refs stay as they were, so the state before the fetch is
recoverable.

A cloud instance is always on a network the repository answers to. Such a
host uses its own read-only credential in the usual way. The bundle is
for the host that is not.

Install the application into the same virtual environment. Use
`--no-deps`, so that it does not change the versions that step 4
recorded:

```bash
~/venvs/venv_3.13/bin/pip install --no-deps -e <application directory>
```

*Proved by:* `git log source/<branch>` on the host shows the commit the
deployment runs, and that commit matches the record for this host.

### Each host has its own key for each outbound link

A link from the host to a receiver, for example an SSH tunnel, uses a
key. **Make a new key on each host.** Do not copy the key of another
host. Add each public key to the receiver separately, so that one host
can be removed without a change to the others.

```bash
ssh-keygen -t ed25519 -N "" -C "<account>@<host>-><receiver>" \
  -f ~/.ssh/id_ed25519_<receiver>
```

Add an entry to `~/.ssh/config` that names the key, with
`IdentitiesOnly yes`. A tunnel that runs with `BatchMode=yes` does not
find a key with a non-standard name without this entry, and it does not
ask. It stops, and `respawn.sh` tries again each 30 s.

### Which commit a host runs, and how to be sure

Record the commit for every host, and read the ancestry in a clone that
**has fetched**:

```bash
git merge-base --is-ancestor <older> <newer> && echo "one line, not a fork"
```

A clone whose remote-tracking refs are older than the last push reports a
commit as unreachable when it is only not fetched yet. That reads exactly
like a fork, and it is not one. Several hosts at different commits on one
branch are usually behind, not divergent.

Catch the branch up with its main line **before** a host is updated, not
after. Then every host goes to the same commit, and is tested there. A
host left behind runs code that no longer matches the repository, and
nobody can say what it runs without reading that host.

## 8. Acceptance

Run in order, and record the result for each host.

1. The identity differs from every other host.
2. The bus answers at each expected address.
3. `aiko_power_manager sample` reports the real device and a reading.
4. `aiko_power_manager verify` reports three artifacts.
5. The service is enabled and active, and lists its entries.
6. The Dashboard draws this host's pages from another computer.
7. The sounds: at boot, and for a button press.
8. **Undocked behavior, on the bench.** Remove the supply and watch the
   host report itself undocked, tell the writers to stop, and then stop
   itself. This is the one check that needs a person at the hardware, and
   it is the one that proves the deployment.
9. The application captures, and its queue drains.

## 9. Before the host ships

Not before: a host being built needs the networks of the people building
it.

- Remove every network profile that the deployment does not need, and
  any near-duplicate left from testing.
- Reduce the keys to what the deployment needs.
- **Empty the store and forward queue.** A host that arrives with a
  backlog uploads it the moment it reaches the network it was built for.
  The already-delivered cache is a cache: the sweep removes it. Anything
  undelivered is a decision, not a clean-up.
- Confirm the development account holds nothing that should not leave.

## What this document will grow into

It covers one kind of host well and the others in outline. The intent is
that it becomes the single general procedure for bringing up any Aiko
Services system, with no deployment's private names in it:

- **The cloud instance**: the provider's own identity step, no bus and
  no hardware, and what a host without a panel reports instead.
- **The developer's computer**: the shortest path to a running
  ProcessManager, which is also the path a new contributor takes.
- **The Actors a host runs**, and which need hardware: the Display, the
  power manager, the Recorder, the StoreForward pair.
- **The hardware notes**, by board: what a Pi 4 does that a Pi 5 does
  not, and the opposite.
- **A fleet inventory**, so that a fleet can be read at a glance: which
  host is which kind, where it is, and what it runs. The host inventory
  below is the part for one host.

Each section is written when a host of that kind is built, and not
before. Every section here was written while a host was built. Each one
gained a step that reading alone had not found.

## What a backup must hold

A backup of the account directories and `/etc` is **not a whole host**.
Three things live outside both, and a host rebuilt without them is wrong
in ways that are hard to see:

| | |
|---|---|
| `/boot/firmware` | the boot configuration, including the bus and the storage |
| `/var/spool/cron` | a scheduled job is invisible without it |
| `/usr/lib/systemd/system-shutdown` | the shutdown hook, which is rendered, so this one costs nothing |

## Host inventory, for a declarative port

The steps above say how a host was made. A port to a declarative
system, for example NixOS, needs **what the host is**. Record these for
each host. Each row becomes one option or one module.

| Kind | What to record | Read it with |
|---|---|---|
| Board and image | The board model, the image date, the kernel | `cat /proc/device-tree/model`, `cat /etc/rpi-issue`, `uname -r` |
| Boot configuration | Each active line, and each `[section]` | `grep -v '^#' /boot/firmware/config.txt`, `cmdline.txt` |
| Kernel modules | The modules loaded at boot | `/etc/modules`, `/etc/modules-load.d/` |
| Operating system packages | The packages installed by a person | `apt-mark showmanual` |
| Python packages | The exact versions in the virtual environment | `pip list --local --format=freeze` |
| Accounts | Each account, its groups and its shell | `id <account>`, `getent passwd` |
| Privilege | Each `sudoers` grant | `/etc/sudoers.d/` |
| Device access | Each `udev` rule that is not from a package | `/etc/udev/rules.d/` |
| Services | Each unit: command, account, directory, environment, order, restart | `systemctl cat <unit>`, `systemctl show <unit>` |
| Shutdown hook | The file and its mode | `/usr/lib/systemd/system-shutdown/` |
| Scheduled jobs | Each crontab | `crontab -l`, `/var/spool/cron` |
| Network | Each interface and its address; each connection profile; the access point | `ip -br addr`, `nmcli con show <profile>` |
| Message broker | The listener and the access rules | `/etc/mosquitto/` |
| Name service | The mDNS settings | `/etc/avahi/avahi-daemon.conf` |
| Identity | The machine id, the SSH host keys, the NetworkManager secret key | `host_declone.sh --show` |
| Per-host values | The host name, the access point SSID, the camera, the outbound keys | This document, steps 2 and 7 |
| Code | The repository, the branch and the commit of each checkout | `git log -1` |
| Definitions | The ProcessManager definition variants, and the one that is selected | `readlink ~/<host>_supervisor.json` |

Two rows are not configuration, and a port must not copy them from
another host:

- **The identity.** A declarative system makes it on the first boot.
- **The outbound keys.** Make them on the host, as step 7 says.

