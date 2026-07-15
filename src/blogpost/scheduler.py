from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path
import subprocess


TASK_NAME = "BlogPostPublisher-Daily"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(slots=True)
class WindowsTaskScheduler:
    executable: Path
    working_dir: Path
    arguments: str = "run-daily"

    def build_install_script(self, schedule_time: time) -> str:
        execute = _ps_quote(str(self.executable))
        workdir = _ps_quote(str(self.working_dir))
        at = _ps_quote(schedule_time.strftime("%H:%M"))
        name = _ps_quote(TASK_NAME)
        return (
            f"$action=New-ScheduledTaskAction -Execute {execute} -Argument {_ps_quote(self.arguments)} -WorkingDirectory {workdir}\n"
            f"$trigger=New-ScheduledTaskTrigger -Daily -At {at}\n"
            "$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)\n"
            f"Register-ScheduledTask -TaskName {name} -Action $action -Trigger $trigger -Settings $settings -Description '每日生成并发布 51CTO AI 博文' -Force | Out-Null"
        )

    def install(self, schedule_time: time) -> None:
        self._run(self.build_install_script(schedule_time))

    def remove(self) -> None:
        self._run(
            f"Unregister-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Confirm:$false -ErrorAction SilentlyContinue"
        )

    def status(self) -> str:
        script = (
            f"$t=Get-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -ErrorAction SilentlyContinue\n"
            "if($null -eq $t){'未安装'}else{($t.State.ToString())}"
        )
        return self._run(script).strip()

    @staticmethod
    def _run(script: str) -> str:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Windows 计划任务操作失败")
        return completed.stdout
