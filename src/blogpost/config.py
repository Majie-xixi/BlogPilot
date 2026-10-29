from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import time
import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


DEFAULT_API_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"
LEGACY_API_BASE_URL = "https://api.deepseek.com/v1"
LEGACY_MODEL = "deepseek-chat"


@dataclass(slots=True)
class ModelConnection:
    id: str
    name: str
    kind: str
    vendor: str = ""
    base_url: str = ""
    model: str = ""


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@dataclass(slots=True)
class AppConfig:
    history_dir: Path = field(default_factory=lambda: Path.home() / "Documents" / "BlogPilot")
    generated_dir: Path = field(
        default_factory=lambda: Path.home() / "Documents" / "BlogPilot" / "generated_posts"
    )
    schedule_time: time = time(10, 0)
    api_base_url: str = DEFAULT_API_BASE_URL
    model: str = DEFAULT_MODEL
    provider: str = "api"
    connections: list[ModelConnection] = field(default_factory=list)
    active_connection_id: str = ""
    category: str = "AI 智能体"
    profile_url: str = ""
    dry_run: bool = True
    min_chinese_chars: int = 800
    target_min_chars: int = 1500
    target_max_chars: int = 3000
    title_similarity_threshold: float = 0.76
    content_similarity_threshold: float = 0.68

    def __post_init__(self) -> None:
        self.history_dir = Path(self.history_dir)
        self.generated_dir = Path(self.generated_dir)
        if not _is_relative_to(self.generated_dir, self.history_dir):
            raise ConfigError("generated directory must be inside history directory")
        if self.generated_dir.resolve() == self.history_dir.resolve():
            raise ConfigError("generated directory must differ from history directory")
        if not 0 <= self.schedule_time.hour <= 23:
            raise ConfigError("invalid schedule time")

    def validate_for_run(self) -> None:
        if self.connections:
            connection = self.current_connection()
            if connection.kind not in {"api", "codex"}:
                raise ConfigError("invalid model provider")
            if connection.kind == "api" and (not connection.model.strip() or not connection.base_url.strip()):
                raise ConfigError("API base URL and model are required")
        else:
            self._validate_legacy_model()
        if self.min_chinese_chars < 401:
            raise ConfigError("minimum article length must exceed 400")
        if self.profile_url and not self.profile_url.startswith("https://blog.51cto.com/u_"):
            raise ConfigError("51CTO profile URL must look like https://blog.51cto.com/u_123456")

    def _validate_legacy_model(self) -> None:
        if self.provider not in {"api", "codex"}:
            raise ConfigError("invalid model provider")
        if self.provider == "api":
            if not self.model.strip():
                raise ConfigError("model is required")
            if not self.api_base_url.strip():
                raise ConfigError("API base URL is required")

    def current_connection(self) -> ModelConnection:
        for connection in self.connections:
            if connection.id == self.active_connection_id:
                return connection
        raise ConfigError("active model connection not found")

    def ensure_connections(self) -> None:
        if self.connections:
            return
        if self.provider not in {"api", "codex"}:
            raise ConfigError("invalid model provider")
        self.connections = [
            ModelConnection("legacy-api", "DeepSeek" if "deepseek.com" in self.api_base_url else "API 服务", "api", "DeepSeek" if "deepseek.com" in self.api_base_url else "自定义", self.api_base_url, self.model),
            ModelConnection("codex", "Codex CLI", "codex"),
        ]
        self.active_connection_id = "codex" if self.provider == "codex" else "legacy-api"

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["history_dir"] = str(self.history_dir)
        data["generated_dir"] = str(self.generated_dir)
        data["schedule_time"] = self.schedule_time.strftime("%H:%M")
        return data

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "AppConfig":
        allowed = {item.name for item in fields(cls)}
        values = {key: value for key, value in data.items() if key in allowed}
        # Migrate the original defaults while preserving genuinely custom providers.
        if values.get("api_base_url") == LEGACY_API_BASE_URL:
            values["api_base_url"] = DEFAULT_API_BASE_URL
        if values.get("model") == LEGACY_MODEL:
            values["model"] = DEFAULT_MODEL
        for name in ("history_dir", "generated_dir"):
            if name in values:
                values[name] = Path(values[name])
        if "schedule_time" in values and isinstance(values["schedule_time"], str):
            hour, minute = values["schedule_time"].split(":", 1)
            values["schedule_time"] = time(int(hour), int(minute))
        if "connections" in values:
            values["connections"] = [ModelConnection(**item) for item in values["connections"]]
        cfg = cls(**values)
        if "connections" not in values:
            cfg.ensure_connections()
        return cfg

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            return cls.for_data_dir(path.parent)
        return cls.from_json_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def for_data_dir(cls, data_dir: Path) -> "AppConfig":
        articles = Path(data_dir) / "articles"
        return cls(
            history_dir=articles,
            generated_dir=articles / "generated_posts",
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(self.to_json_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(path)
