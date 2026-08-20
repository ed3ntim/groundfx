# SPDX-License-Identifier: GPL-3.0-or-later
"""Tiny logging helper with a debug switch wired to the addon preferences.

Usage::

    from ..utils import log
    log.info("domain created: %s", obj.name)
    log.debug("socket map: %r", mapping)   # only shown when debug is on

Keeping this in one place means every module logs with the same prefix and
the same on/off switch, instead of scattering ``print`` calls.
"""
from __future__ import annotations

import logging

from ..core.constants import ADDON_NAME

_logger = logging.getLogger(ADDON_NAME)
_logger.propagate = False

if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(f"[{ADDON_NAME}] %(levelname)s: %(message)s"))
    _logger.addHandler(_handler)

_logger.setLevel(logging.INFO)


def set_debug(enabled: bool) -> None:
    """Flip verbose logging on or off (driven by the addon preferences)."""
    _logger.setLevel(logging.DEBUG if enabled else logging.INFO)


def debug(msg: str, *args) -> None:
    _logger.debug(msg, *args)


def info(msg: str, *args) -> None:
    _logger.info(msg, *args)


def warning(msg: str, *args) -> None:
    _logger.warning(msg, *args)


def error(msg: str, *args) -> None:
    _logger.error(msg, *args)
