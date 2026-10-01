# Aiko Services example: an Actor that draws on an OLED

`oled_actor.py` is one small Actor that owns an SSD1306 128x64 OLED
and draws what remote clients ask for. It shows one idea: an Actor that
owns a device and accepts commands from the network.

The Actor accepts three commands of the `display:0` protocol: `clear`,
`log` and `text`. Thus the clients of the full Display Actor drive it
without change.

## Hardware

An SSD1306 on I2C bus 1 of a Linux Single Board Computer (SBC), at
address 0x3C or 0x3D. The wiring and the I2C set-up are in the
[Display Actor ReadMe](../../actors/display/ReadMe.md#hardware).
Without the panel, the example draws in the terminal.

## Run

Start an MQTT server and the Aiko Services Registrar first
(`scripts/system_start.sh`). Then:

```bash
./oled_actor.py -a 0x3C -n my_oled
```

On a desktop, or with `-a none`, the picture is drawn in the terminal.

## Drive it

```bash
aiko_display -n my_oled text 0 8 Aloha
aiko_display -n my_oled log hello world
aiko_display -n my_oled clear
aiko_display -n my_oled exit      # blank the panel and end the Actor
```

The origin is at the bottom-left: `text 0 0` writes on the bottom row,
`text 0 56` on the top row. `log` scrolls the picture up one row and
writes on the bottom row. You can also send a raw S-expression to the
Actor's `in` topic:

```bash
mosquitto_pub -t TOPIC_PATH/in -m "(text 0 0 hello)"
```

The Dashboard page of the Display Actor also shows this Actor
(`aiko_dashboard -p aiko_services.main.dashboard_plugins -p
aiko_services.actors.display.dashboard_plugin`). The page shows
"mirror: not supported by this Actor". Its keys reach the Actor, which
has no `key` command: the Actor logs an ERROR, "Function not found", on
its log topic for each key.

## This example and the Display Actor

| | This example | The Display Actor (`aiko_display`) |
|---|---|---|
| Size | one file, about 130 lines | a package, about 5000 lines |
| Commands | `clear`, `log`, `text` | the `Canvas`, `Screen` and `Interaction` aspects of `display:0` |
| Shared state | the Actor's default | settings, applets, keys, metrics, a frame mirror |
| Outputs | an SSD1306 or the terminal | an SSD1306, a desktop window, the terminal, PNG files |

## Next step

Read the [Display Actor documents](../../../../documentation/actors/display/ReadMe.md).
`oled_test.py` in this directory is the original standalone spike that
started the work. It is kept for reference and no module imports it.
