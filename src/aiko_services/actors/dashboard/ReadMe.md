# Aiko Services: the Aiko Dashboard

A terminal user interface for every Service on the message bus: what is
running, what each one publishes, and a page for each kind of Service.

```bash
aiko_dashboard                       # the pages below, with no flag
aiko_dashboard --plugin MODULE ...   # and the pages that MODULE registers
```

## The files

| File | What it holds |
|---|---|
| `dashboard.py` | The application: the Dashboard page, the Log page, the plug-in registry and the `aiko_dashboard` console script |
| `frames.py` | The plug-in interface: `FrameCommon`, `ServiceFrame` and `LogUI` |
| `plugins.py` | The default registry. It names the pages and holds no code of its own |
| `registrar_plugin.py` | The Registrar's page: the Services it knows about |
| `process_manager_plugin.py` | The ProcessManager's page: the process table, the posture and its functions |

## Writing a page

A page is a module with a `plugins` dictionary, keyed by the Service name
or by the protocol type. The Dashboard derives that key from the selected
Service, so `.../process_manager:0` selects the page registered as
`process_manager`.

```python
from aiko_services.actors.dashboard import LogUI, ServiceFrame

class ExampleFrame(ServiceFrame):
    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name="example_frame")
        # ... add each Layout and Widget ...
        self.log_ui = LogUI(self)
        self.fix()                 # necessary: asciimatics needs it

    def _service_frame_start(self, service, service_ec_consumer):
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        self.log_ui._service_frame_stop(service)

    def _update(self, frame_no):
        super()._update(frame_no)
        # ... set each Widget from self.dashboard.ec_consumer.cache ...
        self.log_ui._update(frame_no)

plugins = {"example": ExampleFrame}
```

Three rules that the existing pages follow:

- **Read the Dashboard's own ECConsumer**, `self.dashboard.ec_consumer`.
  A page that makes a second consumer of one producer holds a second
  lease, and the Dashboard already holds one.
- **Keep the decisions out of the frame.** `ProcessManagerPage` takes a
  key code or a replica of the shared state and returns what to do or
  what to show. asciimatics has no screen double, so a decision inside a
  frame is a decision no test reaches.
- **Name the part the directory does not say.** A page for a framework
  Service lives here and names the Service, as
  `process_manager_plugin.py` does. A page for an Actor lives with that
  Actor and names the dashboard, as
  `actors/display/dashboard_plugin.py` does.

## Tests

```bash
pytest src/aiko_services/tests/unit/test_dashboard.py \
       src/aiko_services/tests/unit/test_process_manager_plugin.py
```

`tests/unit/dashboard_screen.py` builds a frame on a real curses screen,
on a pseudo-terminal, and draws it twice. It is how the frames are tested
at all: a constructor that forgets `fix()`, a widget taller than its
frame, or an attribute that `_update()` reads too early each raise the
first time a person opens the page, and never before.

It does not cover the update loop over time, key events through
`process_event()`, the popup dialogues, or a terminal resize. Those still
need a person to look.
