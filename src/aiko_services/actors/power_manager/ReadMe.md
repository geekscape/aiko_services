# Aiko Services actors: the PowerManager Actor

What the supply and the battery pack are doing, and what to do about it
(protocol `power_manager:0`).  The main use is a host that runs on a
battery pack and must put itself away safely when the supply goes.  It
reads the voltages, currents and temperatures, decides, and publishes
every reading and every decision as shared state.  It writes a telemetry
log.  Where a deployment allows it, it also holds its own power on,
warns the applications that write to disk, and stops the host.

`aiko_power_manager --help` is the complete command reference, and
`aiko_power_manager sample` is the first thing to run on a new host: one
reading, with no Actor and no message bus in the way.

## The parts

| File | What it holds |
|---|---|
| `power_manager.py` | The Interface, the thresholds, and the Actor behavior every Implementation shares |
| `policy.py` | The decision, as pure functions.  No device, no clock of its own, no Actor |
| `mock.py` | The registered default Implementation.  A platform with no Implementation of its own gets this one, and says so |
| `pmm.py` | The battery module: two INA260 current monitors and an AT30TSE temperature sensor on I2C |
| `ina260.py`, `at30tse.py` | The two device drivers |
| `button.py` | The soft power button and the dock line |
| `hold.py` | The power hold, through the platform's pin utility |
| `signal.py` | The buzzer, and the five patterns |
| `quiesce.py` | Flush the file systems, then remount them read-only |
| `shutdown.py` | The power-off itself |
| `render.py` | The systemd unit, the shutdown hook and the privilege grant |
| `log.py` | The telemetry log: one JSON object for each sample |
| `powered_up.py` | The powered-up Lease: a client asks a host to stay up |
| `cli.py` | The command line |
| `dashboard_plugin.py` | The Aiko Dashboard page |

## The Dashboard page

```bash
aiko_dashboard -p aiko_services.actors.power_manager.dashboard_plugin
```

Select the `power_manager` Service and press Enter.  Three views, which
`v` cycles: a summary of what an operator acts on, the detail of every
item, and an Information view that explains every word this Actor
publishes.  `I` goes straight to it.  The log fills the bottom quarter.

A threshold is changed from the detail view, a group at a time, with
Enter.  The voltages form a ladder, so they are edited together rather
than one at a time.

## The postures, and what each one allows

| Posture | Default | Meaning |
|---|---|---|
| `--safe` | yes | Only `sample`, `set_log_level`, `request_powered_up` and `report_working` are accepted from the message bus |
| `--unsafe` | | Also `hold`, `signal`, `set_period` and `set_threshold`, each of which can stop a host or reach a person |
| `--advisory` | yes | A threshold that came from a data sheet is published and acted on by nothing |
| `--enforce` | | Those thresholds act |

`--advisory` is not "do nothing".  The button, the deployment's deadline
and the backstop on an undocked hold act whatever the posture is: a
person, a dock line and a clock need no calibration, and refusing to act
on them is how a battery pack gets drained flat.

## Running it

```bash
aiko_power_manager sample                   # one reading, no Actor
aiko_power_manager run --device mock        # an Actor on any platform
aiko_power_manager verify                   # what is installed
```

The mock moves on its own.  A laptop therefore runs the whole Actor, the
policy, the Dashboard page and the tests, with no hardware at all.

A real deployment needs three artifacts: the systemd unit, the shutdown
hook and the privilege grant.  `aiko_power_manager render` shows them,
and `install` writes them.  Both need root.  The hook is what releases
the power hold when the host stops.

## What is written down elsewhere

- `constitution/adr/ADR-028_PowerManagement.md`: the design record, and
  the seventeen decisions behind it
- The command line's own help: every option, with its default and the
  reason for it
- Each module's docstring: this package explains itself where the code
  is, rather than in a document that drifts from it
