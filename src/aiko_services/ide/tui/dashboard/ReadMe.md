# Aiko Services: the Aiko Dashboard

A terminal user interface for every Service on the message bus: what is
running, what each one publishes, and a page for each kind of Service.

It lives under `ide/`, and not in an Actor tier, because it is something
a person uses rather than something a running system is made of. `tui/`
says which kind of interface it is.

```bash
aiko_dashboard                       # the pages below, with no flag
aiko_dashboard --plugin MODULE ...   # and the pages that MODULE registers
```

## The files

| File | What it holds |
|---|---|
| `dashboard.py` | The application: the Dashboard page, the Log page, the plug-in registry and the `aiko_dashboard` console script |
| `frames.py` | The plug-in interface: `FrameCommon`, `ServiceFrame`, `LogUI`, `FormFrame` and `ListRequest` |
| `plugins.py` | The default registry. It names the pages and holds no code of its own |
| `category_plugin.py` | The Category's page: its Entries as a tree, and the functions add, remove and update. The model it shows is `main/category_view.py` |
| `hyperspace_plugin.py` | The HyperSpace's page: the Category page, where a whole Entry path opens in place |
| `process_manager_plugin.py` | The ProcessManager's page: the process table, the posture, its functions, and a definition held in a Category |
| `recorder_plugin.py` | The Recorder's page: the topics it records, the newest record of each one, and the filters |
| `registrar_plugin.py` | The Registrar's page: the Services it knows about |

The Dashboard hides Categories from its Service list, because a
HyperSpace of any size has a great many of them. Press `f` then `c` on the
Dashboard page to show them, then `Enter` to open the Category page.

## The ProcessManager's definition

The ProcessManager page shows a definition held in a Category beside the
processes that are running, and matches them by command line. An Entry is
a process when its storage URL begins with `process:`, and what follows is
one definition entry as JSON; its lifecycle manager URL names the
ProcessManager. `main/process_definition.py` holds that convention, and
`aiko_process run` still reads its JSON file when it starts, so editing the
Category changes what a person then starts, and never what is running.

## Writing a page

A page is a module with a `plugins` dictionary, keyed by the Service name
or by the protocol type. The Dashboard derives that key from the selected
Service, so `.../process_manager:0` selects the page registered as
`process_manager`.

```python
from aiko_services.ide.tui.dashboard import LogUI, ServiceFrame

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
- **Keep the model out of the page.** What a page shows of a Service is
  often not about terminals at all, and a REPL, a web page or another
  language's client each need it. `main/category_view.py` holds a
  Category's Entries and the graph they form, and `category_plugin.py`
  holds only what a terminal adds.
- **A dialogue of more than one field is a `FormFrame`.** A
  `PopUpDialog` takes its height from its text and does not grow for a
  `Layout`: with one line of text it is five rows, and every widget after
  the first is silently clipped. A `Text` widget whose value is never set
  raises on its first draw, so give every one a value.
- **Ask the Dashboard to change the selection**, with
  `self.dashboard.select_service(topic_path)`, when a page follows a
  reference from one Service to another. The Category page follows an
  Entry that way. It returns False when the Registrar no longer knows
  that Service, and changes nothing.
- **Name the part the directory does not say.** A page for a framework
  Service lives here and names the Service, as
  `process_manager_plugin.py` does. A page for an Actor lives with that
  Actor and names the dashboard, as
  `actors/display/dashboard_plugin.py` does.

## Tests

```bash
pytest src/aiko_services/tests/unit/test_dashboard.py \
       src/aiko_services/tests/unit/test_category_view.py \
       src/aiko_services/tests/unit/test_process_definition.py \
       src/aiko_services/tests/unit/test_category_plugin.py \
       src/aiko_services/tests/unit/test_hyperspace_plugin.py \
       src/aiko_services/tests/unit/test_process_manager_plugin.py \
       src/aiko_services/tests/unit/test_recorder_plugin.py
```

`tests/unit/dashboard_screen.py` builds a frame on a real curses screen,
on a pseudo-terminal, and draws it twice. It is how the frames are tested
at all: a constructor that forgets `fix()`, a widget taller than its
frame, or an attribute that `_update()` reads too early each raise the
first time a person opens the page, and never before.

It does not cover the update loop over time, key events through
`process_event()`, the popup dialogues, or a terminal resize. Those still
need a person to look.
