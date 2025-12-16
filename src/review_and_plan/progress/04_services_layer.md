# Services Layer Analysis

## Overview
The services layer provides high-level business logic and coordination between infrastructure, domain, and UI layers.

## ProjectFileWatcher (services/file_watcher.py)
**Purpose**: Monitor project directory and emit media discovery events

### Architecture
- **Dual Backend**: Watchdog (preferred) or Qt QFileSystemWatcher (fallback)
- **Polling**: Optional periodic scanning (default 30s)
- **Debouncing**: 250ms delay before processing changes
- **Event-driven**: Publishes to EventHub

### Features
1. **File Discovery**
   - Supported extensions: `.png`, `.jpg`, `.jpeg`, `.bmp`
   - Recursive directory scanning
   - Filters hidden directories (starting with `_`)
   - Allows underscored filenames

2. **Watchdog Backend** (preferred)
   - Uses `watchdog` library (optional dependency)
   - Real-time filesystem events
   - Handles: created, moved, deleted
   - Bridges to Qt via `QMetaObject.invokeMethod`

3. **Qt Backend** (fallback)
   - Uses `QFileSystemWatcher`
   - Directory change notifications
   - Less granular than watchdog

4. **Polling Mode**
   - Configurable interval (default 30s)
   - Can be disabled if watchdog available
   - Fallback when neither backend works
   - Logs poll ticks for debugging

### Event Publishing
- **MediaDiscovered**: New files found
  - Payload: `MediaDiscovered(directory, items)`
  - Items include path, checksum (None), added_at timestamp
- **MediaRemoved**: Files deleted
  - Payload: `MediaRemoved(directory, paths)`

### API
- `watch(directory, known_paths)`: Start monitoring
- `stop()`: Stop monitoring
- `set_polling_enabled(bool)`: Enable/disable polling
- `set_poll_interval_seconds(float)`: Configure poll frequency
- `poll_mode_description()`: Get current mode string

### Configuration
- `WATCHDOG_AVAILABLE`: Global flag for watchdog availability
- Environment: None (configured via preferences)

## ProjectCacheManager (services/cache_manager.py)
**Purpose**: Manage temporary cache data under project directory

### Cache Structure
```
<project>/
└── _cache/
    ├── sessions/
    │   ├── session-20231207120000/
    │   │   ├── workspace1/
    │   │   └── workspace2/
    │   └── session-20231207130000/  (latest, kept)
    └── persistent/
        ├── workspace1/
        └── workspace2/
```

### Features
1. **Session Management**
   - Auto-creates timestamped session directories
   - Prunes all but newest session
   - Format: `session-YYYYMMDDHHmmss`

2. **Workspace Types**
   - **Session-scoped**: Deleted on session prune
   - **Persistent**: Survives session changes

### API
- `session_workspace(name)`: Get/create session workspace
- `persistent_workspace(name)`: Get/create persistent workspace
- `prune_except_latest()`: Clean old sessions
- `clear_workspace(name, persistent)`: Remove workspace
- `list_workspace_files(name, persistent)`: List files

### Usage Pattern
```python
cache = ProjectCacheManager(project_dir)
temp_dir = cache.session_workspace("augmented_data")
persistent_dir = cache.persistent_workspace("model_cache")
cache.prune_except_latest()  # Clean old sessions
```

## Service Exports (services/__init__.py)
The services module exports:

### Core Services
- `ProjectFileWatcher` - File system monitoring
- `ProjectCacheManager` - Cache management
- `DatasetSplitService` - Dataset splitting logic
- `TrainingPersistence` - Training data persistence

### Training Services
- `TrainingExecutionService` - Training orchestration
- `TrainingJobManager` - Job queue management
- `TrainingBackend` - Abstract backend interface
- `LocalTrainingBackend` - Local training execution
- `RemoteTrainingBackend` - Remote training execution
- `TrainingWorkerResult` - Worker result type

### Training Worker Registry
- `register_training_worker(name, worker)` - Register worker
- `register_family_worker(family, worker)` - Register family worker
- `register_runtime_worker(runtime, worker)` - Register runtime worker
- `get_training_worker(spec)` - Get worker for spec
- `available_training_workers()` - List available workers

## Integration Points

### With EventHub
- **ProjectFileWatcher** publishes:
  - `MEDIA_DISCOVERED` events
  - `MEDIA_REMOVED` events

### With MainWindow
- **ProjectFileWatcher**: Created in MainWindow.__init__
  - Configured with poll interval from preferences
  - Polling can be disabled if watchdog available
- **ProjectCacheManager**: Created when project loaded
  - Used for temporary training data
  - Used for augmented dataset exports

### With Infrastructure
- Uses **PersistenceQueue** pattern (not directly, but similar)
- Coordinates with **JsonProjectRepository** for data access

## Design Patterns
1. **Observer Pattern**: FileWatcher publishes events
2. **Strategy Pattern**: Dual backend (watchdog/Qt)
3. **Singleton-like**: One watcher per MainWindow
4. **Session Management**: Cache manager with pruning
5. **Workspace Pattern**: Named cache directories

## Configuration
- Poll interval: From `preferences.file_watcher_poll_seconds`
- Poll enabled: From `preferences.file_watcher_poll_enabled`
- Watchdog: Auto-detected at import time
- Fallback: Always enabled if watchdog unavailable
