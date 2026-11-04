"""Opt-in browser-local CANO colony backup helper."""
from __future__ import annotations

def encode_browser_colony_backup(snapshot):
    raise NotImplementedError("Browser colony backup not implemented")

def decode_browser_colony_backup(report):
    raise NotImplementedError("Browser colony restore not implemented")

def browser_write_confirmed(report, write):
    raise NotImplementedError("Readback not implemented")

def browser_colony_component(*, write=None, clear=False):
    raise NotImplementedError("Browser frontend not implemented")
