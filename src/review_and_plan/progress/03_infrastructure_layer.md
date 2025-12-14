# Infrastructure Layer Analysis

## PersistenceQueue (infrastructure/persistence_queue.py)
**Purpose**: Reusable background persistence queue for debounced file writes

### Architecture
- **Pattern**: Producer-Consumer with debouncing
- **Threading**: Uses ThreadPoolExecutor (max_workers=1)
- **Signals**: `jobFinished(object)`, `jobFailed(object, object)`

### Key Components
1. **Merge Callback** (`merge_func`)
   - Called on GUI thread after debounce timer fires
   - Receives: pending keys, full_refresh flag, queued payloads
   - Updates local caches
   - Returns True if snapshot should be taken

2. **Snapshot Callback** (`snapshot_func`)
   - Called after successful merge
   - Returns immutable payload for background worker
   - Returning None cancels save

3. **Save Callback** (`save_func`)
   - Runs in ThreadPoolExecutor
   - Performs actual disk I/O
   - Returns True/False/None for success status

### Features
- **Debouncing**: Configurable delay (default 250ms)
- **Queue Management**: 
  - `max_pending_jobs`: Limit pending snapshots
  - `drop_oldest_pending`: Control which jobs to drop
- **Lifecycle**: 
  - `enqueue()`: Add diff to queue
  - `flush()`: Immediate flush without waiting
  - `finish()`: Flush and wait for all jobs
  - `shutdown()`: Complete shutdown
  - `pause()`/`resume()`: Suspend processing

### Usage Pattern
```python
queue = PersistenceQueue(
    merge_func=self._merge_cache,
    snapshot_func=self._snapshot_cache,
    save_func=self._save_to_disk,
    debounce_ms=400,
    max_pending_jobs=1
)
queue.enqueue(keys={path}, payload=annotation_set)
```

## UserStoragePaths (user_storage.py)
**Purpose**: User storage directory management for persistent application data

### Storage Structure
```
~/.datalens/  (or custom root)
├── preferences.json
├── ui_state.json
├── logs/
│   ├── datalens.log
│   └── datalens-crash.log
└── models/
    ├── base/
    └── published/
```

### Key Features
1. **Pointer System**
   - Pointer file: `user_storage.json` (in package dir)
   - Environment variable: `DATALENS_USER_STORAGE_POINTER`
   - Allows custom storage location

2. **Migration Support**
   - Legacy root: `{package_dir}/user_data`
   - New default: `~/.datalens`
   - Automatic migration of preferences, UI state, models

3. **Seed Files**
   - Copies default preferences.json and ui_state.json
   - Seeds from previous storage on migration

### API
- `active_user_storage()`: Get current storage (singleton)
- `set_user_storage_root(root)`: Change storage location
- `load_user_storage(root, persist, seed_defaults)`: Load/create storage

## Logging System (logging_config.py)
**Purpose**: Central logging configuration with crash handling

### Architecture
- **Queue-based logging**: Non-blocking file writes
- **Dual log files**:
  - `datalens.log`: Main application log (rotating, 5MB, 5 backups)
  - `datalens-crash.log`: Crash-specific log (rotating, 5MB, 3 backups)

### Components
1. **Main Logger**
   - Uses `QueueHandler` → `QueueListener` pattern
   - Writes to rotating file handler
   - Optional console output (env: `RSCAPTURE_CONSOLE_LOG`)
   - Formatter: `%(asctime)s [%(levelname)s] %(name)s - %(message)s`

2. **Crash Logger** (`datalens.crash`)
   - Synchronous writes (no queue)
   - Separate handler to avoid losing fatal events
   - Does not propagate to root logger

3. **Crash Handlers**
   - `faulthandler`: Dumps traceback on segfaults
   - Signal handlers: SIGSEGV, SIGILL, SIGFPE, SIGABRT, SIGTERM
   - `sys.unraisablehook`: Logs unraisable exceptions
   - `threading.excepthook`: Logs thread exceptions
   - Qt message handler: Routes Qt messages to Python logging

### Lifecycle
- `configure_logging(storage, level)`: Initialize logging
- `install_crash_handlers(storage)`: Enable crash detection
- `shutdown_logging()`: Flush and close all handlers

## Integration Points
- **MainWindow**: Uses PersistenceQueue for annotation saves
- **App startup**: Configures logging and crash handlers early
- **All modules**: Use standard Python logging (routed through queue)
- **Storage**: All persistent data goes through UserStoragePaths

## Design Patterns
1. **Singleton**: UserStoragePaths (active_user_storage)
2. **Producer-Consumer**: PersistenceQueue with debouncing
3. **Queue-based I/O**: Logging system
4. **Callback Pattern**: PersistenceQueue (merge/snapshot/save)
