---
title: Provision a host to run Aiko Services 24 hours a day
description: The sequence that turns a new single-board computer into a
  host that runs the ProcessManager, the power manager and an
  application, and the de-clone step that a copied host must not skip
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

```bash
aiko_power_manager render unit           # read them first: this writes nothing
sudo aiko_power_manager install unit hook grant
aiko_power_manager verify
```

- the unit asserts the power hold at boot and sounds `booted`
- the shutdown hook is the only thing that releases the hold
- the grant is two exact commands, with absolute paths and no wildcard

*Proved by:* `verify` reports all three present, and the hold is asserted
after a reboot.

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

## What a backup must hold

A backup of the account directories and `/etc` is **not a whole host**.
Three things live outside both, and a host rebuilt without them is wrong
in ways that are hard to see:

| | |
|---|---|
| `/boot/firmware` | the boot configuration, including the bus and the storage |
| `/var/spool/cron` | a scheduled job is invisible without it |
| `/usr/lib/systemd/system-shutdown` | the shutdown hook, which is rendered, so this one costs nothing |
