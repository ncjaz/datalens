from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, Flag, auto
from typing import NewType, Optional

DataSourceId = NewType("DataSourceId", int)


class DataSourceKind(Enum):
    """
    High-level type of data source.

    - LOCAL_SQL: default SQLite-backed project database.
    - REMOTE_API: remote server (e.g. another DataLens instance).
    - PLUGIN: provided by a plugin.
    """

    LOCAL_SQL = "local_sql"
    REMOTE_API = "remote_api"
    PLUGIN = "plugin"


class DataSourceCapability(Flag):
    """
    Which operations a data source supports.
    """

    NONE = 0
    READ_MEDIA = auto()
    WRITE_MEDIA = auto()
    READ_ANNOTATIONS = auto()
    WRITE_ANNOTATIONS = auto()
    READ_MODELS = auto()
    WRITE_MODELS = auto()

    FULL = READ_MEDIA | WRITE_MEDIA | READ_ANNOTATIONS | WRITE_ANNOTATIONS | READ_MODELS | WRITE_MODELS


@dataclass(frozen=True)
class DataSource:
    """
    Domain description of a storage backend.

    Concrete implementations live in services/infra; plugins can register
    new data sources by adding records that respect this contract.
    """

    id: DataSourceId
    name: str
    kind: DataSourceKind
    capabilities: DataSourceCapability
    plugin_id: Optional[str] = None  # non-None when provided by a plugin
    config_key: Optional[str] = None  # key for associate_
