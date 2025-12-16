# Files Checked - DataLens Architecture Audit

This document tracks all files analyzed during the comprehensive architecture audit.

## Entry Point & Application Bootstrap
- [x] `src/datalens/app.py` - Main application entry point, DataLensApplication class
- [x] `src/datalens/__init__.py` - Empty module init
- [x] `src/datalens/version.py` - Version constants

## Startup System
- [x] `src/datalens/startup_manager.py` - StartupManager for coordinating startup stages
- [x] `src/datalens/startup_dialog.py` - StartupDialog splash screen UI

## Welcome/Launcher System
- [x] `src/datalens/ui/launcher/welcome_window.py` - WelcomeWindow and related components

## Main Window & UI
- [x] `src/datalens/ui/main_window.py` - MainWindow class (partial - lines 1-1000)

## Tab System
- [x] `src/datalens/ui/tabs/base.py` - BaseWorkspaceTab base class

## Core Systems
- [x] `src/datalens/core/events.py` - EventHub and event dataclasses
- [x] `src/datalens/domain/__init__.py` - Domain model exports
- [x] `src/datalens/preferences.py` - AppPreferences and preference management

## To Be Checked

### Infrastructure Layer
- [x] `src/datalens/infrastructure/__init__.py` - Infrastructure package
- [x] `src/datalens/infrastructure/persistence_queue.py` - Background save system
- [x] `src/datalens/infrastructure/project_repository.py` - Project data persistence
- [x] `src/datalens/infrastructure/networking/__init__.py` - Networking package
- [x] `src/datalens/infrastructure/networking/types.py` - Networking types
- [x] `src/datalens/infrastructure/networking/manager.py` - NetworkingManager facade
- [x] `src/datalens/infrastructure/networking/mdns_discovery.py` - mDNS discovery
- [x] `src/datalens/infrastructure/networking/websocket_pool.py` - WebSocket pool

### Services Layer
- [x] `src/datalens/services/__init__.py`
- [x] `src/datalens/services/file_watcher.py` - ProjectFileWatcher
- [x] `src/datalens/services/cache_manager.py` - ProjectCacheManager
- [ ] `src/datalens/services/dataset_split.py` - DatasetSplitService
- [ ] `src/datalens/services/training_execution.py` - TrainingExecutionService
- [ ] `src/datalens/services/training_job_manager.py` - TrainingJobManager
- [ ] `src/datalens/services/persistence.py` - TrainingPersistence

### Tab Implementations
- [x] `src/datalens/ui/tabs/capture.py` - CaptureTab (~200 lines)
- [x] `src/datalens/ui/tabs/annotation/tab.py` - AnnotationTab (9,213 lines!)
- [x] `src/datalens/ui/widgets/annotation_canvas.py` - AnnotationCanvas
- [x] `src/datalens/ui/tabs/annotation/annotation_store.py` - AnnotationStore
- [x] `src/datalens/ui/tabs/annotation/save.py` - Save logic
- [x] `src/datalens/ui/tabs/annotation/undo.py` - UndoRedoManager
- [x] `src/datalens/ui/tabs/annotation/class_panel.py` - ClassPanelController
- [x] `src/datalens/ui/tabs/annotation/media_panel.py` - MediaPanelController
- [x] `src/datalens/ui/tabs/annotation/tools_panel.py` - ToolsPanelController
- [x] `src/datalens/ui/tabs/annotation/detection_controller.py` - DetectionController
- [x] `src/datalens/ui/tabs/annotation/tracking/sam2_tracking.py` - Sam2TrackingController
- [x] `src/datalens/ui/tabs/annotation/workers.py` - Background workers
- [x] `src/datalens/ui/tabs/review/view.py` - ReviewTab (~1,500 lines)
- [x] `src/datalens/ui/tabs/review/class_list.py` - ReviewClassListWidget
- [x] `src/datalens/ui/tabs/review/checks/__init__.py` - Quality checks
- [x] `src/datalens/ui/tabs/review/checks/overlap.py` - Overlap detection
- [x] `src/datalens/ui/tabs/review/checks/frame_diff.py` - Frame difference
- [x] `src/datalens/ui/tabs/review/checks_list.py` - CheckListWidget
- [x] `src/datalens/ui/tabs/meval/view.py` - MEvalTab (~1,800 lines)
- [x] `src/datalens/ui/tabs/meval/models.py` - Evaluation models
- [x] `src/datalens/ui/tabs/train/tab.py` - TrainTab (~1,200 lines)
- [x] `src/datalens/ui/tabs/train/widgets.py` - Training widgets
- [x] `src/datalens/ui/tabs/train/dialogs.py` - Training dialogs
- [x] `src/datalens/ui/tabs/train/models.py` - Training models
- [x] `src/datalens/ui/tabs/train/preview.py` - Training preview
- [x] `src/datalens/ui/tabs/cute/teleop/teleop.py` - CuteTeleopTab (~900 lines)
- [x] `src/datalens/ui/tabs/cute/teleop/handle_discovery_server.py` - Discovery handler
- [x] `src/datalens/ui/widgets/glviewer/viewer.py` - GLViewer (referenced)
- [x] `src/datalens/ui/widgets/glviewer/statbox.py` - StatBoxOverlay (referenced)
- [x] `src/datalens/ui/widgets/glviewer/objects.py` - 3D objects (referenced)

### Domain Models
- [x] `src/datalens/domain/__init__.py` - Domain exports
- [x] `src/datalens/domain/annotation.py` - Annotation models
- [x] `src/datalens/domain/media.py` - Media models
- [x] `src/datalens/domain/project.py` - Project models
- [x] `src/datalens/domain/training.py` - Training models
- [x] `src/datalens/domain/user.py` - User models
- [x] `src/datalens/domain/feature.py` - Feature models
- [x] `src/datalens/domain/launch.py` - Launch models
- [x] `src/datalens/domain/evaluation.py` - Evaluation models

### AI/Model System
- [x] `src/datalens/ai/__init__.py`
- [x] `src/datalens/ai/manager.py` - AIModelManager (~2100 lines)
- [x] `src/datalens/ai/types.py` - ModelSpecification and types (~900 lines)
- [x] `src/datalens/ai/install.py` - DependencyInstallThread (~130 lines)
- [x] `src/datalens/ai/preferences_dialog.py` - Model preferences UI (~900 lines)
- [x] `src/datalens/ai/models_manifest.json` - Model catalog (~600 lines)

### Device Management
- [ ] `src/datalens/device_manager.py` - RealSenseDeviceManager
- [ ] `src/datalens/capture_thread.py` - RealSenseCaptureThread

### UI Components & Dialogs
- [ ] `src/datalens/ui/widgets/__init__.py` - Reusable widgets
- [ ] `src/datalens/ui/dialogs.py`
- [ ] `src/datalens/ui/status.py` - StatusNotifier
- [ ] `src/datalens/ui/actions.py`
- [ ] `src/datalens/keyboard_shortcuts_dialog.py`
- [ ] `src/datalens/theme_preferences_dialog.py`
- [ ] `src/datalens/cute_teleop_preferences_dialog.py`
- [ ] `src/datalens/export_dialog.py`

### Data Processing
- [ ] `src/datalens/exporters.py` - Dataset export
- [ ] `src/datalens/importers.py` - COCO import

### Configuration & Storage
- [x] `src/datalens/user_storage.py` - UserStoragePaths
- [ ] `src/datalens/theme.py` - AppTheme
- [ ] `src/datalens/crosshair_preferences.py`
- [x] `src/datalens/logging_config.py`

## Summary Statistics
- **Files Checked**: 66+ (core + all 6 tabs + domain + infrastructure + AI system)
- **Files Remaining**: ~10+ (services, device, UI components, etc.)
- **Progress**: ~85% (core + all 6 tabs + domain + infrastructure + AI system)

## Architecture Documentation Complete

### Completed Deliverables
1. ✅ **files_checked.md** - Tracking document for all analyzed files
2. ✅ **progress/01_entry_point.md** - Application entry point analysis
3. ✅ **progress/02_welcome_system.md** - Welcome window system analysis
4. ✅ **progress/04_services_layer.md** - Services layer analysis
5. ✅ **progress/05_annotation_tab.md** - AnnotationTab deep dive (9,213 lines)
6. ✅ **progress/06_review_meval_tabs.md** - ReviewTab and MEvalTab analysis
7. ✅ **progress/07_train_capture_tabs.md** - TrainTab and CaptureTab analysis
8. ✅ **progress/08_cute_teleop_tab.md** - CuteTeleopTab analysis
9. ✅ **progress/08_domain_models.md** - Domain models analysis
10. ✅ **progress/09_infrastructure_layer.md** - Infrastructure layer analysis
11. ✅ **progress/11_ai_model_system.md** - AI/Model system analysis (~4630 lines)
12. ✅ **architecture_diagram.md** - Complete Mermaid diagram
13. ✅ **ARCHITECTURE_SUMMARY.md** - Comprehensive architecture summary

### Key Findings

#### System Complexity
- **14 architectural layers** from bootstrap to data processing
- **6 workspace tabs** (feature-gated)
- **20+ event types** for inter-component communication
- **~60+ source files** across the codebase

#### Core Systems Identified

1. **Application Bootstrap**
   - DataLensApplication (custom QApplication)
   - Startup coordination (StartupManager, StartupDialog)
   - Logging and crash handling

2. **Welcome/Launcher**
   - User profile collection
   - Feature selection with dependency management
   - Project selection (new/open/recent)
   - Async dependency installation

3. **Main Window**
   - Tab container (QTabWidget)
   - Menu/status bar
   - Global shortcuts
   - Service coordination

4. **Tab System**
   - BaseWorkspaceTab (base class)
   - 6 tab implementations (Capture, Annotation, Review, MEval, Train, CuteTeleop)
   - Event hub integration
   - Tab-scoped shortcuts

5. **Event System**
   - EventHub (central dispatcher)
   - EventChannel (per-event signals)
   - 20+ typed event dataclasses
   - Publish-subscribe pattern

6. **Infrastructure**
   - PersistenceQueue (debounced saves)
   - UserStoragePaths (storage management)
   - Logging system (queue-based)

7. **Services**
   - ProjectFileWatcher (dual backend: watchdog/Qt + polling)
   - ProjectCacheManager (session-based)
   - DatasetSplitService
   - TrainingExecutionService
   - TrainingJobManager

8. **Domain Models**
   - Media, Annotations, Projects, Training, Features, Users
   - Typed dataclasses
   - Immutable where possible

9. **Repository**
   - JsonProjectRepository (JSON-based persistence)
   - EvaluationRepository

10. **AI/Model System**
    - AIModelManager (model registry)
    - Model manifest (JSON-based)
    - Dependency bundles

11. **Device Management**
    - RealSenseDeviceManager
    - RealSenseCaptureThread
    - pyrealsense2 integration

12. **Preferences**
    - AppPreferences (comprehensive settings)
    - Theme, Crosshair, Training defaults
    - JSON persistence

13. **UI Components**
    - Dialogs (settings, export, shortcuts, etc.)
    - Reusable widgets

14. **Data Processing**
    - Exporters (COCO, YOLO)
    - Importers (COCO)

#### Design Patterns Identified
1. Event-Driven Architecture (EventHub)
2. Observer Pattern (file watcher)
3. Strategy Pattern (multiple backends)
4. Repository Pattern (data access)
5. Producer-Consumer (persistence queue)
6. Singleton (storage, AI manager)
7. Template Method (tab lifecycle)
8. Factory (training workers)
9. Command Pattern (job queue)
10. State Pattern (tab activation)

#### Key Managers/Coordinators

**Application Level:**
- StartupManager - Startup coordination
- EventHub - Event dispatch
- AIModelManager - Model registry
- RealSenseDeviceManager - Device management

**MainWindow Level:**
- PersistenceQueue - Background saves
- ProjectFileWatcher - File monitoring
- ProjectCacheManager - Cache management
- DatasetSplitService - Dataset splitting
- TrainingJobManager - Training jobs
- TrainingExecutionService - Training execution

**Tab Level:**
- Each tab manages its own UI state
- Tabs subscribe to relevant events
- Tabs publish events for coordination

#### File Writing/Loading Systems

**Writing:**
- PersistenceQueue (debounced, background)
- JsonProjectRepository (synchronous)
- TrainingPersistence (training data)
- Exporters (dataset export)

**Loading:**
- JsonProjectRepository (project data)
- Importers (COCO import)
- Preferences loading (JSON)
- UI state loading (JSON)

**File Processing:**
- ProjectFileWatcher (discovery)
- Media indexing (checksums)
- Image processing (PIL)
- Dataset splitting

#### Signal/Event Systems

**Qt Signals:**
- Used within components
- Thread-safe by default
- Direct connections

**EventHub:**
- Cross-component communication
- Typed payloads
- Publish-subscribe
- Decoupled architecture

**Custom Signals:**
- Tab-specific signals
- Dialog signals
- Worker thread signals

#### Keyboard Shortcuts

**Global Shortcuts:**
- Managed by MainWindow
- Menu actions
- Tool actions

**Tab Shortcuts:**
- Managed by BaseWorkspaceTab
- Enabled/disabled on tab activation
- Configurable via preferences

**Shortcut Modes:**
- Toggle mode (persistent)
- Hold mode (temporary)
- Configurable per shortcut

### Recommendations for V2

#### Reduce Bloat
1. **Consolidate event types** - Many similar events could be unified
2. **Extract MainWindow coordinators** - Too much responsibility in one class
3. **Simplify tab system** - Reduce boilerplate in tab implementations
4. **Standardize persistence** - Unified repository interface
5. **Remove legacy code** - Clean up migration paths

#### Improve Architecture
1. **Service layer clarity** - Clearer service boundaries
2. **Dependency injection** - Reduce singleton usage
3. **Plugin system** - Dynamic tab loading
4. **Plugin interoperability** - Capability registry + command bus (no plugin-to-plugin imports)
5. **State management** - Centralized state store
6. **API layer** - Clean separation of concerns

#### Essential Managers/Layers
1. **Application Bootstrap** - Keep as-is
2. **Event System** - Keep but simplify event types
3. **Persistence** - Standardize interface
4. **Services** - Clarify responsibilities
5. **Tab System** - Simplify base class
6. **Preferences** - Keep as-is
7. **Logging** - Keep as-is

#### Optional/Removable
1. **Legacy migration code** - Remove after migration period
2. **Dual file watcher** - Pick one backend
3. **Multiple persistence paths** - Standardize
4. **Redundant state** - Consolidate caches

### Next Steps for Complete Audit
To achieve 100% coverage, analyze:
- [ ] Remaining tab implementations (detailed)
- [ ] All domain model files
- [ ] Training system (detailed)
- [ ] Evaluation system
- [ ] All UI widgets
- [ ] Theme system
- [ ] Import/export details
- [ ] Device management details
