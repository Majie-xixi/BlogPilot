from __future__ import annotations

import os
import subprocess


METERED_COST_TYPES = {"Fixed", "Variable", "OverDataLimit", "Roaming"}


def internet_connection_status() -> bool | None:
    """Read Windows' local connectivity state without contacting a test website."""
    if os.name != "nt":
        return None
    script = (
        "$ErrorActionPreference='Stop';"
        "$type=[Windows.Networking.Connectivity.NetworkInformation,"
        "Windows.Networking.Connectivity,ContentType=WindowsRuntime];"
        "$profile=$type::GetInternetConnectionProfile();"
        "if($null -eq $profile){'None'}"
        "else{$profile.GetNetworkConnectivityLevel().ToString()}"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    level = completed.stdout.strip()
    if level == "InternetAccess":
        return True
    if level in {"None", "LocalAccess", "ConstrainedInternetAccess"}:
        return False
    return None


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
