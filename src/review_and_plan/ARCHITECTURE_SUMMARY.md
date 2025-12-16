# DataLens Architecture - Comprehensive Summary

## Executive Summary

DataLens is a Qt-based desktop application for data collection, annotation, and model training. The architecture follows a layered design with event-driven communication, featuring:

- **14 distinct architectural layers** from application bootstrap to data processing
- **Event-driven architecture** using a central EventHub for decoupled communication
- **6 workspace tabs** for different workflows (Capture, Annotation, Review, MEval, Train, CuteTeleop)
- **Dual-backend file watching** (watchdog + Qt fallback + polling)
- **Background persistence** with debounced saves
- **Pluggable AI model system** with dependency management
- **Session-based caching** with automatic cleanup

## System Overview

### Core Philosophy
1. **Event-Driven**: Components communicate via EventHub, not direct calls
2. **Layered Architecture**: Clear separation of concerns
3. **Async I/O**: Background workers for file operations
4. **Pluggable Tabs**: Feature-based workspace tabs
5. **Preference-Driven**: Extensive user configuration
6. **Crash-Resilient**: Comprehensive logging and crash handling

### Key Statistics
- **~60+ source files** across multiple layers
- **6 workspace tabs** (feature-gated)
- **20+ event types** for inter-component communication
- **3 persistence backends** (JSON, SQLite, file-based)
- **2 file watcher backends** (watchdog, Qt)
- **Dual logging** (main + crash logs)

## Architectural Layers (Top to Bottom)

### 1. Application Bootstrap Layer
**Files**: `app.py`, `version.py`

**Components**:
- `main()`: Entry point with argument parsing
- `DataLensApplication`: Custom QApplication with event profiling
- Slow event detection (threshold: 75ms)
- Crash logging integration

**Responsibilities**:
- Parse CLI arguments (`--skip-welcome`, `--load-last-project`)
- Initialize Qt application
- Configure logging and crash handlers
- Coordinate startup sequence
- Enter Qt event loop

### 2. Startup Coordination Layer
**Files**: `startup_manager.py`, `startup_dialog.py`

**Components**:
- `StartupManager`: Stage coordination with logging
- `StartupDialog`: Visual progress indicator
- Stage tracking and timing

**Responsibilities**:
- Display startup progress
- Log startup stages
- Coordinate async initialization
- Keep UI responsive during startup

### 3. Welcome/Launcher Layer
**Files**: `ui/launcher/welcome_window.py`

**Components**:
- `WelcomeWindow`: Main dialog
- `_UserProfileForm`: Profile collection
- `_ProfileSummary`: Profile display
- `_ProfileEditDialog`: Profile editing
- `_FeatureSelector`: Feature grid
- `_FeatureCard`: Individual feature toggle
- `_RecentProjectsPanel`: Project list
- `DependencyInstallThread`: Async pip install

**Responsibilities**:
- Collect user profile (name, email)
- Select enabled features
- Check feature dependencies
- Install missing dependencies
- Choose/create project
- Configure preferences
- Create LaunchRequest

**Key Features**:
- Async dependency installation with progress
- Feature dependency validation
- Subproject merge detection
- System diagnostics report
- Recent project management

### 4. Main Window Layer
**Files**: `ui/main_window.py`

**Components**:
- `MainWindow`: Central QMainWindow
- `QTabWidget`: Tab container
- Menu bar (File, Edit, View, Select, Tools, Help)
- Status bar with StatusNotifier
- Keyboard shortcut management
- Device management (RealSense)

**Responsibilities**:
- Host workspace tabs
- Manage global shortcuts
- Coordinate services
- Handle project loading/saving
- Manage device capture
- Export/import datasets
- Preferences dialogs

**Key Features**:
- Deferred tab creation (performance)
- Project state management
- Annotation persistence queue
- Training job coordination
- Model selection
- Theme management

### 5. Tab System Layer
**Files**: `ui/tabs/base.py`, `ui/tabs/*.py`

**Base Class**: `BaseWorkspaceTab`
- Event hub integration
- Shortcut management (tab-scoped)
- Lifecycle hooks (activate/deactivate)
- State persistence

**Tab Implementations**:

1. **CaptureTab** (`ui/tabs/capture.py`)
   - RealSense device capture
   - Device configuration
   - Live preview
   - Capture to project directory

2. **AnnotationTab** (`ui/tabs/annotation/tab.py`)
   - Bounding box annotation
   - Class management
   - Annotation canvas
   - Keyboard shortcuts
   - View modes (fade, spotlight, labels)
   - Isolation mode
   - Previous boxes overlay

3. **ReviewTab** (`ui/tabs/review/view.py`)
   - Media review
   - Flagging system
   - Bulk operations
   - Class filtering

4. **MEvalTab** (`ui/tabs/meval/view.py`)
   - Multi-model evaluation
   - Side-by-side comparison
   - Prediction visualization
   - Evaluation metrics

5. **TrainTab** (`ui/tabs/train/tab.py`)
   - Training job management
   - Dataset split configuration
   - Training progress monitoring
   - Run history
   - Model export

6. **CuteTeleopTab** (`ui/tabs/cute/teleop/teleop.py`)
   - Robot teleoperation
   - Target management
   - 3D viewer
   - Discovery server integration

### 6. Core Event System Layer
**Files**: `core/events.py`

**Components**:
- `EventHub`: Central dispatcher (QObject)
- `EventChannel`: Per-event signal wrapper
- Event dataclasses (20+ types)

**Event Categories**:

1. **Media Events**:
   - `MediaListUpdated`: Media list changed
   - `MediaDiscovered`: New files found
   - `MediaRemoved`: Files deleted

2. **Annotation Events**:
   - `AnnotationsChanged`: Annotation updates
   - `IsolationChanged`: Isolation mode toggled
   - `PreviousBoxesVisibilityChanged`: Previous boxes toggled

3. **View Events**:
   - `ViewModeChanged`: View overlay changed
   - `ShortcutModeChanged`: Shortcut mode changed

4. **Training Events**:
   - `TrainingSplitsChanged`: Dataset splits updated
   - `TrainingRunsChanged`: Run history updated
   - `TrainingRunQueued`: Job queued
   - `TrainingRunStarted`: Job started
   - `TrainingRunProgress`: Progress update
   - `TrainingRunCompleted`: Job completed
   - `TrainingRunFailed`: Job failed
   - `TrainingRunRequested`: UI requests training
   - `TrainingRunCancellationRequested`: Cancel requested
   - `TrainingRunDeletionRequested`: Delete requested
   - `TrainingFineTuneRequested`: Fine-tune requested
   - `TrainingAugmentedDatasetRequested`: Export augmented data
   - `TrainingAugmentedDatasetCompleted`: Export completed

5. **Model Events**:
   - `ModelStateChanged`: Project state updated

**Pattern**: Publish-Subscribe with typed payloads

### 7. Infrastructure Layer
**Files**: `infrastructure/persistence_queue.py`, `user_storage.py`, `logging_config.py`

**Components**:

1. **PersistenceQueue**:
   - Debounced background saves
   - ThreadPoolExecutor (1 worker)
   - Merge/snapshot/save callbacks
   - Job queue with limits
   - Pause/resume support

2. **UserStoragePaths**:
   - Storage directory management
   - Pointer system for custom locations
   - Legacy migration support
   - Seed file management

3. **Logging System**:
   - Queue-based logging (non-blocking)
   - Rotating file handlers (5MB, 5 backups)
   - Dual logs (main + crash)
   - Crash handler integration
   - Qt message routing

**Storage Structure**:
```
~/.datalens/
├── preferences.json
├── ui_state.json
├── logs/
│   ├── datalens.log
│   └── datalens-crash.log
└── models/
    ├── base/
    └── published/
```

### 8. Services Layer
**Files**: `services/*.py`

**Components**:

1. **ProjectFileWatcher**:
   - Dual backend (watchdog/Qt)
   - Optional polling (30s default)
   - Debouncing (250ms)
   - Hidden directory filtering
   - Event publishing

2. **ProjectCacheManager**:
   - Session-based caching
   - Automatic session pruning
   - Persistent workspaces
   - Temporary workspaces

3. **DatasetSplitService**:
   - Dataset splitting logic
   - Train/val/test splits
   - Event publishing

4. **TrainingExecutionService**:
   - Training orchestration
   - Worker backend selection
   - Progress monitoring

5. **TrainingJobManager**:
   - Job queue management
   - Event coordination
   - Run history

6. **TrainingPersistence**:
   - Training data persistence
   - Run records
   - Metrics storage

**Cache Structure**:
```
<project>/_cache/
├── sessions/
│   └── session-YYYYMMDDHHmmss/
│       └── workspace_name/
└── persistent/
    └── workspace_name/
```

### 9. Domain Models Layer
**Files**: `domain/*.py`

**Model Categories**:

1. **Media Models**:
   - `MediaItem`: File path, checksum, timestamp
   - `MediaIndex`: Media collection

2. **Annotation Models**:
   - `AnnotationSet`: Annotations for one image
   - `AnnotationBoxRecord`: Bounding box
   - `TagRecord`: Class definition
   - `DEFAULT_TAG_COLOR`: Default color

3. **Project Models**:
   - `ProjectState`: Complete project snapshot
   - `ProjectHistory`: Historical states

4. **Training Models**:
   - `TrainingProjectState`: Training-specific state
   - `TrainingRunRecord`: Single run record
   - `TrainingRunLog`: Run logs
   - `TrainingMetricSnapshot`: Metrics at epoch
   - `DatasetSplitConfig`: Split configuration
   - `ImageSplitAssignment`: Image→split mapping
   - `PreprocessingConfig`: Preprocessing settings
   - `AugmentationConfig`: Augmentation settings
   - `TrainingRequest`: Training job request

5. **Feature Models**:
   - `FeatureDefinition`: Feature metadata
   - `FeatureDependency`: Dependency info
   - `FeatureStatus`: Dependency status

6. **Startup Models**:
   - `LaunchRequest`: Startup configuration
   - `FeatureSelection`: Selected features

7. **User Models**:
   - `UserProfile`: Name and email

8. **Evaluation Models**:
   - `EvaluationRun`: Evaluation session
   - `BoundingBox`: Detection box
   - `Prediction`: Model prediction
   - `GroundTruthObject`: Ground truth
   - `PerClassStats`: Per-class metrics

### 10. Repository/Persistence Layer
**Files**: `infrastructure/project_repository.py`

**Components**:
- `JsonProjectRepository`: JSON-based persistence
- `EvaluationRepository`: Evaluation data
- `media_from_paths()`: Media item creation

**File Structure**:
```
<project>/
├── annotations.json
├── annotation_tags.json
├── flagged_images.json
├── training_splits.json
├── training_runs.json
└── _media_index.sqlite (optional)
```

**Responsibilities**:
- Load/save project state
- Load/save annotations
- Load/save training data
- Media indexing
- Checksum management

### 11. AI/Model System Layer
**Files**: `ai/*.py`

**Components**:
- `AIModelManager`: Model registry
- `ModelSpecification`: Model metadata
- `models_manifest.json`: Model definitions
- `DependencyInstallThread`: Async pip install
- Model preferences dialog

**Features**:
- Model selection
- Dependency bundles
- Favorite models
- Model validation
- Runtime detection

**Manifest Structure**:
```json
{
  "models": [...],
  "dependency_bundles": {
    "bundle_name": {
      "python": ["package1", "package2"]
    }
  }
}
```

### 12. Device Management Layer
**Files**: `device_manager.py`, `capture_thread.py`

**Components**:
- `RealSenseDeviceManager`: Device discovery
- `RealSenseCaptureThread`: Background capture
- pyrealsense2 integration

**Features**:
- Device enumeration
- Stream configuration
- Option management
- Live capture
- Frame processing

### 13. Preferences Layer
**Files**: `preferences.py`, `theme.py`, `crosshair_preferences.py`

**Components**:

1. **AppPreferences**:
   - Theme settings
   - Crosshair settings
   - Recent projects limit
   - Sample media limit
   - Training defaults
   - Keyboard shortcuts
   - Tab state (annotation, review, meval)
   - Navigation timing
   - User profile
   - Enabled features
   - Discovery server config
   - File watcher config
   - Bulk operation limits

2. **AppTheme**:
   - Color scheme
   - Primary/secondary/tertiary colors
   - Text colors
   - Opacity helpers

3. **CrosshairPreferences**:
   - Solid arm length/thickness/color
   - Dotted guide thickness/color/length/spacing/density

4. **TrainSplitDefaults**:
   - Train/val/test percentages
   - Epochs per run

**Persistence**:
- `preferences.json`: Main preferences
- `ui_state.json`: UI state (legacy migration)

### 14. UI Components Layer
**Files**: Various dialog and widget files

**Dialogs**:
- `GeneralPreferencesDialog`: General settings
- `ModelPreferencesDialog`: AI model settings
- `ThemePreferencesDialog`: Theme customization
- `CuteTeleopPreferencesDialog`: Teleop settings
- `ExportDatasetDialog`: Dataset export wizard
- `KeyboardShortcutsDialog`: Shortcut configuration
- `ViewDefaultsDialog`: View mode defaults
- `ProjectAppStateDialog`: Project state viewer
- `SystemStateDialog`: System diagnostics
- `TrainingPreviewDialog`: Training preview

**Widgets**:
- `PillButton`: Rounded button
- `ThemedCheckBox`: Themed checkbox
- `DualRingSpinner`: Loading spinner
- `AutoToggleWidget`: Auto-toggle control
- `SliderOptionWidget`: Slider with label
- `StatusNotifier`: Status bar notifications

### 15. Data Processing Layer
**Files**: `exporters.py`, `importers.py`

**Exporters**:
- COCO format
- YOLO format
- Export configuration
- Error handling

**Importers**:
- COCO import
- Image copying
- Checksum validation
- Error handling

## Key Design Patterns

### 1. Event-Driven Architecture
**Pattern**: Publish-Subscribe via EventHub
**Benefits**: Decoupled components, easy to extend
**Usage**: All inter-component communication

### 2. Observer Pattern
**Pattern**: File watcher publishes events
**Benefits**: Reactive to filesystem changes
**Usage**: ProjectFileWatcher → EventHub

### 3. Strategy Pattern
**Pattern**: Multiple file watcher backends
**Benefits**: Fallback support, platform independence
**Usage**: Watchdog → Qt → Polling

### 4. Repository Pattern
**Pattern**: JsonProjectRepository abstracts persistence
**Benefits**: Testable, swappable backends
**Usage**: All project data access

### 5. Producer-Consumer
**Pattern**: PersistenceQueue with debouncing
**Benefits**: Non-blocking saves, batching
**Usage**: Annotation saves, training data

### 6. Singleton
**Pattern**: Single instance managers
**Benefits**: Global access, resource management
**Usage**: UserStoragePaths, AIModelManager

### 7. Template Method
**Pattern**: BaseWorkspaceTab lifecycle
**Benefits**: Consistent tab behavior
**Usage**: All workspace tabs

### 8. Factory
**Pattern**: Training worker registry
**Benefits**: Pluggable backends
**Usage**: Training execution

### 9. Command Pattern
**Pattern**: Training job queue
**Benefits**: Queuing, cancellation
**Usage**: TrainingJobManager

### 10. State Pattern
**Pattern**: Tab activation/deactivation
**Benefits**: Clean state transitions
**Usage**: Tab shortcut management

## Data Flow Examples

### Annotation Save Flow
```
1. User edits annotation in AnnotationTab
2. Tab updates local cache (_annotation_cache)
3. Tab calls _annotation_persistence.enqueue(keys={path})
4. PersistenceQueue starts debounce timer (400ms)
5. Timer fires → merge_func() called
6. merge_func() updates cache, returns True
7. snapshot_func() creates immutable _AnnotationSaveJob
8. ThreadPoolExecutor submits save_func()
9. save_func() writes to annotations.json
10. jobFinished signal emitted
11. MainWindow updates status bar
```

### Media Discovery Flow
```
1. User adds image to project directory
2. Watchdog detects filesystem event
3. _WatchdogHandler.on_created() called
4. QMetaObject.invokeMethod() to Qt thread
5. ProjectFileWatcher._handle_watchdog_path()
6. Build MediaItem with path, timestamp
7. EventHub.publish(MEDIA_DISCOVERED, payload)
8. AnnotationTab subscribes, receives event
9. Tab updates media list
10. ReviewTab subscribes, receives event
11. Tab updates media list
```

### Training Job Flow
```
1. User configures training in TrainTab
2. User clicks "Start Training"
3. Tab creates TrainingRequest
4. Tab publishes TRAINING_RUN_REQUESTED event
5. TrainingJobManager receives event
6. Manager queues job
7. TrainingExecutionService picks up job
8. Service publishes TRAINING_RUN_STARTED
9. Service executes training (worker backend)
10. Service publishes TRAINING_RUN_PROGRESS (periodic)
11. TrainTab updates progress UI
12. Training completes
13. Service publishes TRAINING_RUN_COMPLETED
14. TrainTab updates run history
15. TrainingPersistence saves run record
```

### Project Load Flow
```
1. User selects project in WelcomeWindow
2. WelcomeWindow creates LaunchRequest
3. WelcomeWindow.accept() returns to app.py
4. app.py creates MainWindow with launch_request
5. MainWindow schedules _apply_loaded_project_state()
6. ThreadPoolExecutor loads project data
7. _project_load_completed signal emitted
8. MainWindow._apply_loaded_project_state() called
9. Update annotation cache
10. Update media list
11. Publish MODEL_STATE_CHANGED event
12. Publish MEDIA_LIST_UPDATED event
13. Tabs receive events and update UI
14. File watcher starts monitoring
15. Cache manager prunes old sessions
```

## Thread Safety

### GUI Thread (Main Thread)
- All Qt widgets
- Event hub publish/subscribe
- PersistenceQueue merge/snapshot
- File watcher event handling
- Tab UI updates

### Worker Threads
- PersistenceQueue save callback
- Training execution
- Dependency installation
- Device metadata loading
- Project data loading
- Model inference

### Thread Communication
- Qt signals (automatically thread-safe)
- QMetaObject.invokeMethod (cross-thread calls)
- ThreadPoolExecutor futures
- Queue-based logging
- Atomic operations on shared state

### Synchronization
- Qt event loop serialization
- Mutex-free design (event-driven)
- Immutable payloads for workers
- Copy-on-write for caches

## Performance Optimizations

### 1. Deferred Tab Creation
- Tabs created after main window shown
- Reduces startup time
- Improves perceived performance

### 2. Debounced Saves
- 400ms debounce for annotations
- Batches rapid changes
- Reduces disk I/O

### 3. Background Workers
- Non-blocking file operations
- Parallel project loading
- Async dependency installation

### 4. Event Batching
- Multiple changes → single event
- Reduces UI updates
- Improves responsiveness

### 5. Cache Management
- Session-based pruning
- Automatic cleanup
- Persistent workspaces for reuse

### 6. Lazy Loading
- Media loaded on demand
- Annotations loaded incrementally
- Models loaded when selected

### 7. Polling Optimization
- Configurable interval (default 30s)
- Can be disabled with watchdog
- Debounced scan results

## Error Handling

### 1. Logging
- Queue-based (non-blocking)
- Rotating files (5MB, 5 backups)
- Separate crash log
- Qt message routing

### 2. Crash Handling
- faulthandler for segfaults
- Signal handlers (SIGSEGV, etc.)
- Unraisable exception hook
- Thread exception hook

### 3. Defensive Programming
- Try-except around I/O
- Graceful degradation
- User-friendly error messages
- Detailed logging for debugging

### 4. Validation
- Preference validation
- Path normalization
- Type checking
- Bounds checking

## Configuration

### Command Line
- `--skip-welcome`: Skip welcome window
- `--load-last-project`: Auto-load recent project

### Environment Variables
- `DATALENS_SLOW_EVENT_THRESHOLD_MS`: Event profiling
- `RSCAPTURE_CONSOLE_LOG`: Console logging
- `DATALENS_USER_STORAGE_POINTER`: Custom storage

### Preferences File
- `~/.datalens/preferences.json`
- JSON format
- Validated on load
- Migrates from legacy ui_state.json

### UI State File
- `~/.datalens/ui_state.json`
- Recent projects
- Window geometry
- Tab state

## Extensibility Points

### 1. New Tabs
- Inherit from BaseWorkspaceTab
- Implement lifecycle hooks
- Subscribe to events
- Register shortcuts

### 2. New Events
- Add dataclass to events.py
- Add constant to EventHub
- Publish from source
- Subscribe in consumers

### 3. New Models
- Add to ai/models_manifest.json
- Define dependencies
- Register worker if needed

### 4. New Export Formats
- Add to exporters.py
- Implement format conversion
- Add to ExportDatasetDialog

### 5. New Preferences
- Add to AppPreferences dataclass
- Add to preferences dialog
- Handle in to_dict/from_mapping

## Testing Considerations

### Unit Testing
- Domain models (pure Python)
- Repository logic
- Data processing
- Utility functions

### Integration Testing
- Event flow
- Service coordination
- File operations
- Persistence

### UI Testing
- Tab lifecycle
- Dialog interactions
- Keyboard shortcuts
- Theme application

### Performance Testing
- Event throughput
- Save performance
- Load performance
- Memory usage

## Future Improvements

### Architecture
1. **Reduce MainWindow complexity**: Extract coordinators
2. **Simplify event types**: Consolidate similar events
3. **Standardize persistence**: Unified repository interface
4. **Plugin system**: Dynamic tab loading
5. **Plugin interoperability**: Capability registry + command bus (optional providers, no plugin-to-plugin imports)
6. **Service layer cleanup**: Clearer responsibilities

### Performance
1. **Incremental loading**: Load media on scroll
2. **Virtual lists**: For large media collections
3. **Caching strategy**: Smarter cache invalidation
4. **Parallel processing**: Multi-threaded operations

### Maintainability
1. **Type hints**: Complete type coverage
2. **Documentation**: API docs for all public methods
3. **Testing**: Increase test coverage
4. **Logging**: Structured logging
5. **Metrics**: Performance monitoring

### Features
1. **Undo/redo**: For annotations
2. **Collaboration**: Multi-user support
3. **Cloud sync**: Remote storage
4. **Mobile app**: Companion app
5. **Web interface**: Browser-based viewer

## Conclusion

DataLens is a well-structured Qt application with clear separation of concerns. The event-driven architecture provides flexibility and extensibility, while the layered design ensures maintainability. Key strengths include:

- **Robust error handling** with comprehensive logging
- **Non-blocking I/O** with background workers
- **Flexible configuration** via preferences
- **Pluggable architecture** for tabs and models
- **Cross-platform support** with fallback mechanisms

Areas for improvement include reducing MainWindow complexity, consolidating similar event types, and standardizing the persistence layer. Overall, the architecture provides a solid foundation for future enhancements.
