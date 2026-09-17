"""Shared subprocess policy for unattended CHARLIE/CORE processes."""

from __future__ import annotations

import os
import subprocess


def background_process_kwargs(platform_name=None):
    """Return flags that prevent unattended children opening terminal windows."""
    platform_name = os.name if platform_name is None else platform_name
    if platform_name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {"start_new_session": True}


def background_run_kwargs(platform_name=None):
    """Return subprocess.run-compatible window suppression flags."""
    platform_name = os.name if platform_name is None else platform_name
    if platform_name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
