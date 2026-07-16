from __future__ import annotations

import os
import subprocess


METERED_COST_TYPES = {"Fixed", "Variable", "OverDataLimit", "Roaming"}


def network_cost_type() -> str:
    """Read Windows connection cost locally without opening a network socket."""
    if os.name != "nt":
        return "Unrestricted"
    script = (
        "$ErrorActionPreference='Stop';"
        "$type=[Windows.Networking.Connectivity.NetworkInformation,"
        "Windows.Networking.Connectivity,ContentType=WindowsRuntime];"
        "$profile=$type::GetInternetConnectionProfile();"
        "if($null -eq $profile){'Unknown'}else{$profile.GetConnectionCost().NetworkCostType.ToString()}"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Unknown"
    return completed.stdout.strip() if completed.returncode == 0 else "Unknown"


def is_metered_connection() -> bool:
    return network_cost_type() in METERED_COST_TYPES
