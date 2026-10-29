from dataclasses import replace

from blogpost.config import AppConfig


class SettingsState:
    """A private draft; switching pages never mutates the running configuration."""

    def __init__(self, config: AppConfig):
        self.original = config
        source = replace(config, connections=[replace(c) for c in config.connections])
        source.ensure_connections()
        self.connections = source.connections
        self.active_id = source.active_connection_id
        self.dry_run = source.dry_run
        self.keys: dict[str, str] = {}
        self.original_ids = {c.id for c in source.connections}
        self.deleted_ids: set[str] = set()

    def remove_connection(self, connection_id: str) -> None:
        if connection_id == self.active_id:
            raise ValueError('请先将其他连接设为当前连接')
        connection = next((c for c in self.connections if c.id == connection_id), None)
        if connection is None or connection.kind != 'api':
            raise ValueError('只能删除 API 连接')
        self.connections.remove(connection)
        self.keys.pop(connection_id, None)
        if connection_id in self.original_ids:
            self.deleted_ids.add(connection_id)

    def configuration(self) -> AppConfig:
        ids = [c.id for c in self.connections]
        if len(ids) != len(set(ids)) or any(not c.name.strip() for c in self.connections):
            raise ValueError('连接名称不能为空，且连接标识不能重复')
        config = replace(self.original, connections=[replace(c) for c in self.connections],
                         active_connection_id=self.active_id, dry_run=self.dry_run)
        config.validate_for_run()
        return config
