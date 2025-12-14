# Progress Note 09: Infrastructure Layer

**Date**: 2024-12-07  
**Status**: Complete  
**Coverage**: Persistence, repositories, networking

## Overview

The infrastructure layer provides low-level services for persistence, networking, and external system integration. It sits between the domain layer (pure data) and the application layer (UI/services).

## Architecture

### Layer Responsibilities

1. **Persistence** - Background file I/O, debouncing, queuing
2. **Repositories** - Domain object serialization/deserialization
3. **Networking** - mDNS discovery, WebSocket management
4. **Assets** - Resource management (not analyzed in detail)

### Design Principles

1. **Domain Independence** - Infrastructure doesn't depend on domain logic
2. **Async Operations** - Non-blocking I/O via Qt threads
3. **Signal-Based** - Qt signals for async completion
4. **Reusability** - Generic components for multiple use cases

## Components

### 1. PersistenceQueue

**File**: `infrastructure/persistence_queue.py`

**Purpose**: Reusable background persistence queue for debounced file writes

**Architecture**:
```
User Edit → enqueue(keys, payload)
         → Debounce Timer (250ms default)
         → merge_func (GUI thread)
         → snapshot_func (GUI thread)
         → Job Queue
         → ThreadPoolExecutor (1 worker)
         → save_func (background thread)
         → jobFinished/jobFailed signals
```

**Key Features**:

1. **Debouncing** - Coalesces rapid edits into single save
2. **Three-Phase Pipeline**:
   - `merge_func`: Update caches on GUI thread
   - `snapshot_func`: Create immutable snapshot
   - `save_func`: Perform I/O on worker thread
3. **Queue Management** - Optional max pending jobs with drop policy
4. **Pause/Resume** - Suspend processing during bulk operations
5. **Flush/Finish** - Force immediate save or wait for completion

**API**:

```python
class PersistenceQueue(QObject):
    jobFinished = Signal(object)
    jobFailed = Signal(object, object)
    
    def __init__(
        self,
        *,
        merge_func: MergeCallback,
        snapshot_func: SnapshotCallback,
        save_func: SaveCallback,
        debounce_ms: int = 250,
        use_worker: bool = True,
        max_pending_jobs: int | None = None,
        drop_oldest_pending: bool = True,
    ):
        ...
    
    def enqueue(
        self,
        *,
        keys: Iterable[Hashable] | None = None,
        payload: Any = None,
        full_refresh: bool = False,
        immediate: bool = False,
    ) -> None:
        """Queue a diff for persistence."""
    
    def flush(self) -> None:
        """Flush pending diffs without waiting."""
    
    def finish(self) -> None:
        """Flush and wait for all jobs."""
    
    def shutdown(self) -> None:
        """Flush, wait, and stop executor."""
    
    def pause(self) -> None:
        """Suspend processing."""
    
    def resume(self, *, flush_pending: bool = True) -> None:
        """Resume processing."""
```

**Callback Signatures**:

```python
MergeCallback = Callable[[set[Hashable], bool, Sequence[Any]], bool]
# Args: (keys, full_refresh, payloads) -> should_snapshot

SnapshotCallback = Callable[[], Any]
# Returns: Immutable payload for save_func

SaveCallback = Callable[[Any], Optional[bool]]
# Args: (payload) -> success (True/False/None)
```

**Usage Pattern**:

```python
def merge(keys, full_refresh, payloads):
    # Update local cache
    for payload in payloads:
        cache.update(payload)
    return True  # Snapshot needed

def snapshot():
    # Create immutable snapshot
    return dataclasses.replace(state)

def save(payload):
    # Perform I/O
    with open(path, 'w') as f:
        json.dump(payload, f)
    return True

queue = PersistenceQueue(
    merge_func=merge,
    snapshot_func=snapshot,
    save_func=save,
    debounce_ms=250,
)

# User edits
queue.enqueue(keys={'image1.jpg'}, payload=annotation_set)
# ... more edits within 250ms ...
# Timer fires → merge → snapshot → background save
```

**Benefits**:

1. **Responsive UI** - I/O doesn't block GUI thread
2. **Efficient** - Coalesces rapid edits
3. **Safe** - Immutable snapshots prevent race conditions
4. **Reusable** - Generic for any persistence need

**Current Users**:

- Annotation save logic (via AnnotationTab)
- Training state persistence (potential)
- Project state persistence (potential)

### 2. JsonProjectRepository

**File**: `infrastructure/project_repository.py`

**Purpose**: Filesystem-backed implementation of ProjectRepository interface

**Responsibilities**:

1. **Serialize/Deserialize** - Domain objects ↔ JSON
2. **File Management** - Read/write project files
3. **Path Normalization** - Relative vs absolute paths
4. **Migration** - Handle legacy formats
5. **Database Integration** - SQLite media index

**File Layout**:

```
project_directory/
├── annotation_tags.json       # TagRecord list
├── annotations.json            # AnnotationSet list + metadata
├── training_splits.json        # Dataset split config + assignments
├── training_runs.json          # Training run history
├── _media_index.sqlite         # Media cache (new)
└── training_outputs/           # Training artifacts
    ├── run_<uuid>/
    │   ├── request.json
    │   ├── logs.jsonl
    │   └── weights/
    └── ...
```

**Key Methods**:

```python
class JsonProjectRepository(ProjectRepository):
    # Tags
    def load_tags(self, directory: Path) -> list[TagRecord]
    def save_tags(self, directory: Path, tags: Sequence[TagRecord]) -> None
    
    # Annotations
    def load_annotations(
        self, directory: Path, media: Sequence[MediaItem]
    ) -> list[AnnotationSet]
    
    def save_annotations(
        self,
        directory: Path,
        annotations: Sequence[AnnotationSet],
        *,
        media: Sequence[MediaItem] | None = None,
        model: ModelSpecification | None = None,
        viewer: Mapping[str, object] | None = None,
    ) -> None
    
    # Training
    def load_training_state(self, directory: Path) -> TrainingProjectState
    def save_training_state(
        self, directory: Path, training: TrainingProjectState
    ) -> None
    
    # Complete state
    def load_state(self, directory: Path, media: Sequence[MediaItem]) -> ProjectState
    def save_state(self, directory: Path, state: ProjectState) -> None
```

**JSON Schemas**:

**annotation_tags.json**:
```json
{
  "version": "0.1.0",
  "tags": [
    {"name": "person", "color": "#FF5733", "count": 42},
    {"name": "car", "color": "#33FF57", "count": 18}
  ]
}
```

**annotations.json**:
```json
{
  "version": "0.1.0",
  "images": {
    "images/img001.jpg": [
      {
        "x": 0.1,
        "y": 0.2,
        "width": 0.3,
        "height": 0.4,
        "tag": "person",
        "confidence": null,
        "track_id": null
      }
    ]
  },
  "media_order": ["images/img001.jpg", "images/img002.jpg"],
  "ai_model": {
    "id": "yolov8n",
    "name": "YOLOv8 Nano",
    "...": "..."
  },
  "viewer": {
    "current_index": 0
  }
}
```

**training_splits.json**:
```json
{
  "version": "0.1.0",
  "config": {
    "splits": [
      {"name": "train", "ratio": 0.8},
      {"name": "val", "ratio": 0.1},
      {"name": "test", "ratio": 0.1}
    ],
    "fallback_split": "train"
  },
  "assignments": [
    {
      "media_path": "images/img001.jpg",
      "split": "train",
      "manual": false
    }
  ],
  "ingest_manifest": {
    "train": [{"path": "images/img001.jpg", "manual": false}],
    "val": [],
    "test": [],
    "unassigned": [],
    "invalid": []
  },
  "preprocessing": {
    "selections": [
      {
        "identifier": "resize",
        "enabled": true,
        "parameters": [["width", 640], ["height", 640]]
      }
    ]
  },
  "augmentation": {
    "selections": [
      {
        "identifier": "horizontal_flip",
        "enabled": true,
        "parameters": []
      }
    ]
  },
  "epochs_per_run": 144
}
```

**training_runs.json**:
```json
{
  "version": "0.1.0",
  "runs": [
    {
      "run_id": "uuid-here",
      "version_name": "v1.0.0",
      "created_at": "2024-12-07T10:00:00Z",
      "dataset_split": {"...": "..."},
      "image_assignments": [],
      "preprocessing": {"...": "..."},
      "augmentation": {"...": "..."},
      "metrics": [
        {
          "recorded_at": "2024-12-07T10:05:00Z",
          "epoch": 1,
          "metrics": [["loss", 0.5], ["accuracy", 0.85]]
        }
      ],
      "notes": "Initial training run",
      "model": {"...": "..."},
      "model_binding": {"...": "..."},
      "output_path": "training_outputs/run_uuid/",
      "published_model_id": null
    }
  ]
}
```

**Path Normalization**:

```python
def _path_for_payload(self, path: Path, base_dir: Optional[Path]) -> str:
    """Return relative path if inside base_dir, else absolute."""
    # Project-local: "images/img001.jpg"
    # External: "/home/user/external/img.jpg"
```

**Benefits**:
- Relative paths for portability
- Absolute paths for external references
- Automatic migration on load

**Migration Strategy**:

1. **Version Key** - Add "version" field if missing
2. **Path Normalization** - Convert absolute → relative for project files
3. **Legacy Formats** - Support old field names ("tag" → "name")
4. **Database Migration** - Populate SQLite on first load

**Database Integration**:

**MediaIndexDB** (`media_index_db.py`):
- SQLite database for media cache
- Stores media order, metadata, tags
- Faster than JSON for large projects
- Migrated from JSON on first load

**Schema**:
```sql
CREATE TABLE media (
    path TEXT PRIMARY KEY,
    dir_path TEXT,
    mtime REAL,
    size INTEGER,
    rgb_ok INTEGER,
    width INTEGER,
    height INTEGER,
    order_index INTEGER
);

CREATE TABLE tags (
    name TEXT PRIMARY KEY,
    color TEXT,
    count INTEGER
);
```

**Error Handling**:

```python
def _write_json(self, path: Path, payload: object) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception:
        # Best-effort: swallow errors so UI continues
        pass
```

**Philosophy**: Persistence failures shouldn't crash the app

### 3. Networking Layer

**Package**: `infrastructure/networking/`

**Purpose**: Unified networking layer for mDNS discovery and WebSocket connections

**Architecture**:

```
NetworkingManager (facade)
├── MdnsDiscovery (zeroconf wrapper)
│   ├── ServiceBrowser (per service type)
│   └── Zeroconf instance
└── WebSocketPool (connection manager)
    └── QWebSocket instances
```

**Design Goals**:

1. **Domain-Agnostic** - Reusable across features
2. **Qt-Integrated** - Signals for async events
3. **Non-Blocking** - Background threads for I/O
4. **Unified API** - Single entry point

#### 3.1 Types

**File**: `networking/types.py`

**Endpoint**:
```python
@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    path: str = "/"
    
    def __str__(self) -> str:
        return f"ws://{self.host}:{self.port}{self.path}"
```

**DiscoveredService**:
```python
@dataclass(frozen=True)
class DiscoveredService:
    name: str                    # "My Robot._cute-robot._tcp.local."
    service_type: str            # "_cute-robot._tcp.local."
    host: str                    # "192.168.1.100"
    port: int                    # 8000
    txt_records: dict[str, str]  # {"version": "1.0.0"}
    
    def to_endpoint(self, path: str = "/") -> Endpoint:
        return Endpoint(host=self.host, port=self.port, path=path)
```

**ConnectionId**:
```python
@dataclass(frozen=True)
class ConnectionId:
    id: str  # UUID
```

#### 3.2 NetworkingManager

**File**: `networking/manager.py`

**Purpose**: Top-level facade for all networking operations

**Signals**:
```python
class NetworkingManager(QObject):
    # mDNS
    mdns_service_added = Signal(DiscoveredService)
    mdns_service_removed = Signal(DiscoveredService)
    mdns_services_updated = Signal(str, list)  # type, services
    
    # WebSocket
    ws_message_received = Signal(ConnectionId, str)
    ws_connection_closed = Signal(ConnectionId)
    ws_connection_error = Signal(ConnectionId, str)
```

**API**:
```python
# Lifecycle
def enable(self) -> None
def disable(self) -> None

# mDNS
def start_mdns(self, service_type: str) -> None
def stop_mdns(self, service_type: str) -> None
def refresh_mdns(self, service_type: str | None = None) -> None
def get_mdns_services(self, service_type: str) -> list[DiscoveredService]

# WebSocket
def connect_endpoint(self, endpoint: Endpoint) -> ConnectionId
def connect_service(self, service: DiscoveredService, path: str = "/") -> ConnectionId
def send_text(self, conn_id: ConnectionId, message: str) -> None
def send_json(self, conn_id: ConnectionId, payload: dict) -> None
def close_connection(self, conn_id: ConnectionId) -> None
def close_all_connections(self) -> None
```

**Usage Pattern**:
```python
from datalens.infrastructure.networking import get_manager

manager = get_manager()
manager.enable()

# Discover robots
manager.start_mdns("_cute-robot._tcp.local.")
manager.mdns_service_added.connect(on_robot_found)

# Connect to robot
def on_robot_found(service: DiscoveredService):
    conn_id = manager.connect_service(service, path="/api")
    manager.ws_message_received.connect(on_message)
    manager.send_json(conn_id, {"command": "status"})

def on_message(conn_id: ConnectionId, message: str):
    data = json.loads(message)
    print(f"Received: {data}")
```

**Global Singleton**:
```python
# Package-level singleton
_GLOBAL_MANAGER: Optional[NetworkingManager] = None

def get_manager() -> NetworkingManager:
    """Return process-global NetworkingManager."""
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = NetworkingManager()
    return _GLOBAL_MANAGER

def set_manager(mgr: Optional[NetworkingManager]) -> None:
    """Set global manager (for tests)."""
    global _GLOBAL_MANAGER
    _GLOBAL_MANAGER = mgr
```

#### 3.3 MdnsDiscovery

**File**: `networking/mdns_discovery.py`

**Purpose**: Qt-friendly mDNS/zeroconf discovery wrapper

**Architecture**:
```
MdnsDiscovery
├── Zeroconf instance
├── ServiceBrowser (per service type)
└── Service cache (dict[str, list[DiscoveredService]])
```

**Signals**:
```python
class MdnsDiscovery(QObject):
    service_added = Signal(DiscoveredService)
    service_removed = Signal(DiscoveredService)
    services_updated = Signal(str, list)  # type, services
```

**API**:
```python
def enable(self) -> None
def disable(self) -> None
def start_service_type(self, service_type: str) -> None
def stop_service_type(self, service_type: str) -> None
def get_services(self, service_type: str) -> list[DiscoveredService]
def refresh(self, service_type: str | None = None) -> None
```

**Implementation Details**:

1. **ServiceBrowser Callback**:
```python
def on_service_state_change(*args, **kwargs):
    # Handle multiple zeroconf callback signatures
    # (name, state_change, info) or
    # (zeroconf, service_type, name, state_change, info)
    
    if state_change == ServiceStateChange.Added:
        self._on_service_added(name, info, service_type)
    elif state_change == ServiceStateChange.Removed:
        self._on_service_removed(name, service_type)
    elif state_change == ServiceStateChange.Updated:
        self._on_service_updated(name, info, service_type)
```

2. **Service Info Conversion**:
```python
@staticmethod
def _service_info_to_discovered(
    name: str, service_type: str, info
) -> DiscoveredService | None:
    # Extract host (prefer IPv4)
    host = None
    if info.addresses:
        for addr in info.addresses:
            host = str(addr)
            if "." in host and ":" not in host:  # IPv4
                break
    
    # Decode TXT records
    txt_records = {}
    if info.properties:
        for key, value in info.properties.items():
            if isinstance(key, bytes):
                key = key.decode("utf-8", errors="replace")
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            txt_records[key] = value
    
    return DiscoveredService(...)
```

**Thread Safety**:
- ServiceBrowser runs in background thread
- Callbacks emit Qt signals → safe cross-thread

#### 3.4 WebSocketPool

**File**: `networking/websocket_pool.py`

**Purpose**: Qt-friendly WebSocket connection pool/manager

**Architecture**:
```
WebSocketPool
├── _connections: dict[str, QWebSocket]
└── _conn_id_map: dict[QWebSocket, ConnectionId]
```

**Signals**:
```python
class WebSocketPool(QObject):
    message_received = Signal(ConnectionId, str)
    connection_closed = Signal(ConnectionId)
    connection_error = Signal(ConnectionId, str)
```

**API**:
```python
def connect_endpoint(self, endpoint: Endpoint) -> ConnectionId
def connect_service(self, service: DiscoveredService, path: str = "/") -> ConnectionId
def send_text(self, conn_id: ConnectionId, message: str) -> None
def send_json(self, conn_id: ConnectionId, payload: dict) -> None
def close(self, conn_id: ConnectionId) -> None
def close_all(self) -> None
```

**Implementation**:

```python
def connect_endpoint(self, endpoint: Endpoint) -> ConnectionId:
    conn_id = ConnectionId(str(uuid.uuid4()))
    ws = QWebSocket()
    
    # Store mapping
    self._connections[conn_id.id] = ws
    self._conn_id_map[ws] = conn_id
    
    # Connect signals
    ws.textMessageReceived.connect(
        lambda msg, ws=ws: self._on_message(ws, msg)
    )
    ws.disconnected.connect(lambda ws=ws: self._on_disconnected(ws))
    ws.error.connect(lambda err, ws=ws: self._on_error(ws))
    
    # Connect
    url = str(endpoint)  # "ws://host:port/path"
    ws.open(url)
    
    return conn_id

def _on_message(self, ws: QWebSocket, message: str) -> None:
    conn_id = self._conn_id_map.get(ws)
    if conn_id:
        self.message_received.emit(conn_id, message)

def _on_disconnected(self, ws: QWebSocket) -> None:
    conn_id = self._conn_id_map.get(ws)
    if conn_id:
        # Clean up
        del self._connections[conn_id.id]
        del self._conn_id_map[ws]
        self.connection_closed.emit(conn_id)
```

**Benefits**:
- Automatic cleanup on disconnect
- Bidirectional mapping for fast lookup
- Qt signal integration for async events

## Data Flow Patterns

### Annotation Save Flow

```
User Edit → AnnotationTab
         → PersistenceQueue.enqueue(keys, payload)
         → Debounce Timer (250ms)
         → merge_func: Update local cache
         → snapshot_func: Create ProjectState snapshot
         → Job Queue
         → ThreadPoolExecutor
         → save_func: JsonProjectRepository.save_state()
         → Write JSON files
         → jobFinished signal
```

### Project Load Flow

```
User Opens Project
→ JsonProjectRepository.load_state(directory, media)
→ MediaIndexDB.load_media_ordered()
→ MediaIndexDB.load_tag_rows()
→ load_annotations_payload()
→ _annotations_from_payload()
→ load_training_state()
→ build_project_state()
→ ProjectState (frozen dataclass)
→ UI updates
```

### mDNS Discovery Flow

```
User Enables Cute Teleop
→ NetworkingManager.enable()
→ MdnsDiscovery.enable()
→ Zeroconf instance created
→ NetworkingManager.start_mdns("_cute-robot._tcp.local.")
→ ServiceBrowser created
→ Background thread discovers services
→ ServiceBrowser callback
→ MdnsDiscovery._on_service_added()
→ mdns_service_added signal
→ NetworkingManager.mdns_service_added signal
→ UI updates device list
```

### WebSocket Communication Flow

```
User Selects Robot
→ NetworkingManager.connect_service(service)
→ WebSocketPool.connect_endpoint(endpoint)
→ QWebSocket.open("ws://host:port/path")
→ Connection established
→ User Sends Command
→ NetworkingManager.send_json(conn_id, payload)
→ WebSocketPool.send_text(conn_id, json_str)
→ QWebSocket.sendTextMessage(json_str)
→ Robot Responds
→ QWebSocket.textMessageReceived signal
→ WebSocketPool._on_message()
→ ws_message_received signal
→ NetworkingManager.ws_message_received signal
→ UI processes response
```

## Strengths

1. **PersistenceQueue**:
   - Excellent abstraction for background saves
   - Reusable across features
   - Proper separation of concerns (merge/snapshot/save)
   - Handles edge cases (pause/resume, flush/finish)

2. **JsonProjectRepository**:
   - Clean separation of persistence logic
   - Handles migrations gracefully
   - Path normalization for portability
   - Database integration for performance

3. **Networking Layer**:
   - Domain-agnostic design
   - Qt-integrated (signals, non-blocking)
   - Unified API via NetworkingManager
   - Reusable across features (Cute Teleop, Cute Lab, etc.)

4. **Type Safety**:
   - Frozen dataclasses for networking types
   - Clear API boundaries
   - Immutable snapshots for thread safety

## Weaknesses

1. **PersistenceQueue**:
   - Complex callback signatures
   - No built-in retry logic
   - Silent error swallowing in save_func

2. **JsonProjectRepository**:
   - Large file with many responsibilities
   - Complex payload parsing logic
   - No schema validation
   - Silent error swallowing

3. **Networking Layer**:
   - No reconnection logic
   - No connection pooling limits
   - No timeout configuration
   - Error handling could be more robust

4. **Documentation**:
   - Limited inline documentation
   - No usage examples in docstrings
   - Complex flows not diagrammed

## Recommendations for V2

### PersistenceQueue Improvements

1. **Add Retry Logic**:
```python
def __init__(
    self,
    *,
    max_retries: int = 3,
    retry_delay_ms: int = 1000,
    ...
):
    ...
```

2. **Add Error Callbacks**:
```python
ErrorCallback = Callable[[Exception, Any], None]

def __init__(
    self,
    *,
    error_func: ErrorCallback | None = None,
    ...
):
    ...
```

3. **Add Metrics**:
```python
@property
def pending_count(self) -> int:
    return len(self._job_queue)

@property
def active_job(self) -> Any | None:
    return self._active_future
```

### JsonProjectRepository Improvements

1. **Add Schema Validation**:
```python
from jsonschema import validate

def _validate_payload(self, payload: dict, schema: dict) -> bool:
    try:
        validate(payload, schema)
        return True
    except ValidationError:
        return False
```

2. **Split into Smaller Classes**:
```python
class TagRepository:
    def load(self, directory: Path) -> list[TagRecord]
    def save(self, directory: Path, tags: Sequence[TagRecord]) -> None

class AnnotationRepository:
    def load(self, directory: Path, media: Sequence[MediaItem]) -> list[AnnotationSet]
    def save(self, directory: Path, annotations: Sequence[AnnotationSet]) -> None

class TrainingRepository:
    def load(self, directory: Path) -> TrainingProjectState
    def save(self, directory: Path, training: TrainingProjectState) -> None

class ProjectRepository:
    def __init__(self):
        self.tags = TagRepository()
        self.annotations = AnnotationRepository()
        self.training = TrainingRepository()
```

3. **Add Logging for Errors**:
```python
def _write_json(self, path: Path, payload: object) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception as e:
        logger.error(f"Failed to write {path}: {e}")
        # Still swallow to keep UI responsive
```

### Networking Layer Improvements

1. **Add Reconnection Logic**:
```python
class WebSocketPool:
    def __init__(
        self,
        *,
        auto_reconnect: bool = True,
        reconnect_delay_ms: int = 5000,
        max_reconnect_attempts: int = 3,
    ):
        ...
```

2. **Add Connection Limits**:
```python
class WebSocketPool:
    def __init__(
        self,
        *,
        max_connections: int = 10,
    ):
        ...
```

3. **Add Timeout Configuration**:
```python
class WebSocketPool:
    def connect_endpoint(
        self,
        endpoint: Endpoint,
        *,
        timeout_ms: int = 5000,
    ) -> ConnectionId:
        ...
```

4. **Add Connection State**:
```python
@dataclass(frozen=True)
class ConnectionState:
    id: ConnectionId
    endpoint: Endpoint
    status: Literal["connecting", "connected", "disconnected", "error"]
    error: str | None = None

class WebSocketPool:
    def get_connection_state(self, conn_id: ConnectionId) -> ConnectionState:
        ...
```

### General Improvements

1. **Add Comprehensive Tests**:
   - Unit tests for each component
   - Integration tests for flows
   - Mock external dependencies (zeroconf, filesystem)

2. **Add Usage Examples**:
   - Docstring examples for each class
   - Standalone example scripts
   - Tutorial documentation

3. **Add Metrics/Monitoring**:
   - Persistence queue depth
   - Save success/failure rates
   - WebSocket connection counts
   - mDNS discovery latency

4. **Add Configuration**:
   - Centralized config for timeouts, retries, etc.
   - Environment variable overrides
   - Runtime configuration updates

## Files Analyzed

- ✅ `src/datalens/infrastructure/__init__.py`
- ✅ `src/datalens/infrastructure/persistence_queue.py`
- ✅ `src/datalens/infrastructure/project_repository.py`
- ✅ `src/datalens/infrastructure/networking/__init__.py`
- ✅ `src/datalens/infrastructure/networking/types.py`
- ✅ `src/datalens/infrastructure/networking/manager.py`
- ✅ `src/datalens/infrastructure/networking/mdns_discovery.py`
- ✅ `src/datalens/infrastructure/networking/websocket_pool.py`

**Total Files**: 8  
**Total Classes**: 6 major classes

## Summary

The infrastructure layer provides solid foundations for persistence and networking. The PersistenceQueue is a well-designed reusable component. The JsonProjectRepository handles complex serialization logic but could benefit from splitting into smaller classes. The networking layer is domain-agnostic and Qt-integrated, making it reusable across features. Main opportunities for improvement are error handling, retry logic, and splitting large classes into smaller, focused components.
