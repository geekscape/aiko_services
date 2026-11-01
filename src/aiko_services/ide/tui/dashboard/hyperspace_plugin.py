#!/usr/bin/env python3
#
# Aiko Services: the HyperSpace's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A HyperSpace is a Category that resolves a whole Entry path and manages
# the Categories along it, so this page is the Category page with the
# differences a HyperSpace makes, and nothing else:
#
# - It resolves a path, so a Category opens in place, as a directory does
#   in a file manager, instead of being followed to its own Service.  One
#   "(list ...)" request for each node is the progressive discovery.
# - add, remove and update name a path, not an Entry name.
# - A Category is created by "create" and destroyed by "destroy", which
#   persist it, rather than by adding a reference to one.
# - It has storage, and metrics, and it can be asked to dump its state.
#
# Registered through "plugins.py", the Dashboard's default "--plugin"
# module, so this page needs no flag.  The key is the protocol type.
#
# Everything else — the Entry syntax, the dialogues, the trail, the state
# table and the log — is "category_plugin.py", which this module
# subclasses twice: once for the decisions, once for the frame.  The tree
# and the cycle check are "main/category_view.py", which neither page
# knows more about than the other.  A HyperSpace Entry that refers to a
# Category Service outside this HyperSpace is still followed by "g", as
# it is on the Category page.
#
# To Do
# ~~~~~
# - Load a whole subtree in one request.  "(list ... recursive)" answers
#   with the name of a nested Category but not its path, so a client
#   cannot place a record below the first level, and this page asks for
#   one path at a time
# - A Category of another HyperSpace, which "hyperspace.py" calls a
#   different root
# - "destroy" only destroys an empty Category.  Offer to destroy what it
#   holds, once "hyperspace.py" removes recursively

from aiko_services.main.category_view import (
    CATEGORY, PATH_DELIMITER, entry_path_join,
)
from aiko_services.ide.tui.dashboard import text_field
from aiko_services.main.hyperspace import HyperSpace
from aiko_services.ide.tui.dashboard.category_plugin import (
    CategoryFrame, CategoryPage,
)

__all__ = ["HyperSpaceFrame", "HyperSpacePage", "plugins"]

class HyperSpacePage(CategoryPage):
    """The Category page's decisions, where a path is resolved"""

    resolves_paths = True

    KEYS = dict(CategoryPage.KEYS, **{
        "c": ("create",),
        "k": ("destroy",),
        "U": ("dump",),
        "K": ("exit",),
    })

    STATE_KEYS = ("entries_count", "storage_url",
        "lifecycle", "log_level", "running")

    def help_lines(self):
        return super().help_lines() + [
            "",
            "A HyperSpace resolves a whole Entry path, so a Category opens",
            "where it is, and its own functions persist what they change:",
            "",
            "  c create   CATEGORY_PATH",
            "  k destroy  the selected Category, when it holds nothing",
            "             (a Category Entry is removed by d, which",
            "             destroys it here, because a HyperSpace owns it)",
            "  U dump     its state, to its log",
            "  K exit     terminate the HyperSpace",
        ]

class HyperSpaceFrame(CategoryFrame):
    """The Dashboard page: the Entry tree, the state, the log"""

    PAGE = HyperSpacePage
    INTERFACE = HyperSpace
    FRAME_NAME = "hyperspace_frame"

    def _act(self, kind):
        if kind == "create":
            self._create()
        elif kind == "destroy":
            self._destroy()
        elif kind == "dump":
            if self._connected():
                self.proxy.dump()
        elif kind == "exit":
            self._confirm_exit()
        else:
            super()._act(kind)

    # What a path names, and how a Category is made and unmade --------- #

    def _entry_path(self, category_path, name):
        """A HyperSpace resolves a path, from its own root"""

        return entry_path_join(category_path, name)

    def _create_category(self, category_path, name, protocol, owner, tags):
        """A HyperSpace creates a Category, and persists it, rather than
        holding a reference to one that is running already"""

        self.proxy.create(self._entry_path(category_path, name))

    def _remove(self, category_path, node):
        """A Category is destroyed, a Dependency is removed"""

        entry_path = self._entry_path(category_path, node.name)
        if node.kind == CATEGORY:
            self.proxy.destroy(entry_path)
        else:
            self.proxy.remove(entry_path)

    # The HyperSpace functions ----------------------------------------- #

    def _create(self):
        category_path = self.page.current_category(self._selected_path())

        def accept(values):
            path = values["path"].strip().strip(PATH_DELIMITER)
            if path and self._connected():
                self.proxy.create(self._entry_path(category_path, path))

        self._form(
            f"Create a Category in {self.page.breadcrumb(category_path)}",
            [text_field("path", "Path")], "Create", accept,
            note="A path of more than one name creates each Category"
                 "\nalong it, as \"mkdir -p\" does.")

    def _destroy(self):
        node = self._selected_node()
        if node is None or node.kind != CATEGORY:
            return self._popup("Select a Category first.", ["OK"])
        path = node.path

        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self.proxy.destroy(path)

        self._popup(
            f"Destroy {self.page.breadcrumb(path)} ?\n\n"
            "A HyperSpace destroys a Category that holds nothing, and"
            "\nleaves one that still holds Entries as it is.",
            ["Cancel", "Destroy"], _on_close)

    def _confirm_exit(self):
        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self.proxy.exit()

        self._popup("Terminate the HyperSpace?\n\n"
            "Its Categories are in its own process, so they terminate"
            "\nwith it.  What is persisted is read again when it runs.",
            ["Cancel", "Exit"], _on_close)

    def _legend_text(self):
        keys = "keys: Enter open  a add  c create  u update  d remove"  \
               "  k destroy  r refresh  f filter  s sort  F clear"  \
               "  U dump  K exit  L log level  H help"
        notes = [note for note in (self._trail_text(), self._diagnostic)
            if note]
        return f"{keys}   {'   '.join(notes)}" if notes else keys

# plugin key: the protocol type of hyperspace:0
plugins = {"hyperspace": HyperSpaceFrame}

# --------------------------------------------------------------------------- #
