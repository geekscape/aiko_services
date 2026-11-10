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
  - src/aiko_services/main/daemon_supervisor/ReadMe.md
  - src/aiko_services/actors/power_manager/ReadMe.md
related: [../concepts/process_manager, ../concepts/dashboard_plugin]
last_updated: 2026-11-08
---

# Provision a host to run Aiko Services 24 hours a day

This is the order in which a host is built, and the reason for each step.
It is written from the hosts that run it, and each step names what proves
that it worked.

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

## 4. Aiko Services

```bash
git clone <this repository> ~/aiko_services
cd ~/aiko_services && git switch master
python3 -m venv ~/venvs/venv_3.13
~/venvs/venv_3.13/bin/pip install -e ~/aiko_services
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
symbolic link that selects one. A host being built points the link at
the variant that starts the platform only.

*Proved by:* `systemctl is-enabled` and `is-active`, then
`aiko_process list` shows the entries.

## 7. The application

The application's own repository, branch and configuration. A host that
cannot reach that repository cannot be completed. Give it access before
this step, rather than during it.

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
- **An inventory**, so that a fleet can be read at a glance: which host
  is which kind, where it is, and what it runs.

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
