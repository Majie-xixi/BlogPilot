from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
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

    def build_install_script(self, schedule_time: time | Iterable[time]) -> str:
        execute = _ps_quote(str(self.executable))
        workdir = _ps_quote(str(self.working_dir))
        times = [schedule_time] if isinstance(schedule_time, time) else list(schedule_time)
        if not times:
            raise ValueError("至少需要一个启用账号的发布时间")
        unique_times = sorted({value.strftime("%H:%M") for value in times})
        trigger_lines = ["$now=Get-Date"]
        for index, value in enumerate(unique_times):
            trigger_lines.extend(
                (
                    f"$at{index}=$now.Date.Add([timespan]{_ps_quote(value)})",
                    f"if($at{index} -le $now){{$at{index}=$at{index}.AddDays(1)}}",
                    f"$trigger{index}=New-ScheduledTaskTrigger -Daily -At $at{index}",
                )
            )
        trigger_names = ",".join(f"$trigger{index}" for index in range(len(unique_times)))
        name = _ps_quote(TASK_NAME)
        return (
            f"$action=New-ScheduledTaskAction -Execute {execute} -Argument {_ps_quote(self.arguments)} -WorkingDirectory {workdir}\n"
            + "\n".join(trigger_lines)
            + "\n"
            + f"$triggers=@({trigger_names})\n"
            "$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)\n"
            f"Unregister-ScheduledTask -TaskName {name} -Confirm:$false -ErrorAction SilentlyContinue\n"
            f"Register-ScheduledTask -TaskName {name} -Action $action -Trigger $triggers -Settings $settings -Description '按账号计划生成并发布 51CTO AI 博文' -Force | Out-Null"
        )

    def install(self, schedule_time: time | Iterable[time]) -> None:
        self._run(self.build_install_script(schedule_time))

    def remove(self) -> None:
        self._run(
            f"Unregister-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Confirm:$false -ErrorAction SilentlyContinue"
        )

    def build_status_script(self) -> str:
        expected_execute = _ps_quote(str(self.executable))
        expected_arguments = _ps_quote(self.arguments)
        expected_workdir = _ps_quote(str(self.working_dir))
        name = _ps_quote(TASK_NAME)
        return (
            f"$t=Get-ScheduledTask -TaskName {name} -ErrorAction SilentlyContinue\n"
            "if($null -eq $t){'Missing'; return}\n"
            "$a=$t.Actions[0]\n"
            "if(-not (Test-Path -LiteralPath $a.Execute -PathType Leaf)){"
            "'Invalid|ExecutableMissing'; return}\n"
            f"$executeOk=[string]::Equals([string]$a.Execute,{expected_execute},"
            "[System.StringComparison]::OrdinalIgnoreCase)\n"
            f"$argumentsOk=[string]::Equals([string]$a.Arguments,{expected_arguments},"
            "[System.StringComparison]::Ordinal)\n"
            f"$workdirOk=[string]::Equals([string]$a.WorkingDirectory,{expected_workdir},"
            "[System.StringComparison]::OrdinalIgnoreCase)\n"
            "if(-not ($executeOk -and $argumentsOk -and $workdirOk)){"
            "'Invalid|ActionMismatch'; return}\n"
            f"$i=Get-ScheduledTaskInfo -TaskName {name}\n"
            "if($t.State -ne 'Running' -and $i.LastRunTime.Year -gt 2000 "
            "-and $i.LastTaskResult -ne 0){"
            "'Failed|' + $i.LastTaskResult; return}\n"
            "$t.State.ToString()"
        )

    def status(self) -> str:
        return self._run(self.build_status_script()).strip()

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
