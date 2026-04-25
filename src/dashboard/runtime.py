from __future__ import annotations

import importlib
import os

from dash import Dash

_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def _read_bool_env(*, name: str, default: bool) -> bool:
    """
    Parses a boolean environment variable.

    args:
        name: Environment variable name to read.
        default: Value to return when the variable is unset.

    returns:
        The parsed boolean flag.
    """
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in _TRUE_ENV_VALUES


def _supports_werkzeug_debugger() -> bool:
    """
    Checks whether the local Python runtime can load Werkzeug's debugger dependency.

    args:
        None.

    returns:
        True when the debugger can be enabled safely.
    """
    try:
        importlib.import_module("_multiprocessing")
    except ImportError:
        return False
    return True


def run_dash_app(*, app: Dash) -> None:
    """
    Runs a Dash app with debugger settings that work under restricted Windows policies.

    args:
        app: Dash application instance to start.

    returns:
        None.
    """
    debug_enabled = _read_bool_env(name="DASH_DEBUG", default=True)
    use_debugger = debug_enabled and _supports_werkzeug_debugger()
    app.run(debug=debug_enabled, use_debugger=use_debugger)
