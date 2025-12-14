# DataLens Architecture Audit - Documentation Index

## Overview

This directory contains a comprehensive architecture audit of the DataLens application. The audit analyzes the codebase to understand system architecture, identify managers and coordinators, document data flows, and provide recommendations for a V2 redesign.

## Documentation Structure

### 📋 Main Documents

1. **[ARCHITECTURE_SUMMARY.md](ARCHITECTURE_SUMMARY.md)** ⭐ **START HERE**
   - Executive summary of the entire system
   - 14 architectural layers explained
   - Key design patterns
   - Data flow examples
   - Thread safety analysis
   - Performance optimizations
   - Future improvement recommendations

2. **[architecture_diagram.md](architecture_diagram.md)** ⭐ **VISUAL REFERENCE**
   - Complete Mermaid diagram of the system
   - All components and their relationships
   - Layer-by-layer breakdown
   - Data flow diagrams
   - Configuration sources
   - Startup/shutdown sequences

3. **[files_checked.md](files_checked.md)** 📊 **PROGRESS TRACKER**
   - List of all files analyzed
   - Checklist of remaining files
   - Progress statistics
   - Key findings summary
   - Recommendations for V2

### 📁 Progress Notes (Detailed Analysis)

Located in `progress/` directory:

1. **[01_entry_point.md](progress/01_entry_point.md)**
   - Application entry point (app.py)
   - DataLensApplication class
   - Startup sequence
   - Command-line arguments
   - Dependencies identified

2. **[02_welcome_system.md](progress/02_welcome_system.md)**
   - WelcomeWindow and components
   - User profile management
   - Feature selection system
   - Dependency installation
   - Project selection
   - Integration points

3. **[03_infrastructure_layer.md](progress/03_infrastructure_layer.md)**
   - PersistenceQueue (background saves)
   - UserStoragePaths (storage management)
   - Logging system (queue-based)
   - Design patterns
   - Integration points

4. **[04_services_layer.md](progress/04_services_layer.md)**
   - ProjectFileWatcher (file monitoring)
   - ProjectCacheManager (cache management)
   - Service exports
   - Configuration
   - Integration with EventHub

5. **[05_annotation_tab.md](progress/05_annotation_tab.md)** ⚠️ **LARGEST COMPONENT**
   - AnnotationTab (9,213 lines!)
   - AnnotationCanvas (interactive overlay)
   - Media discovery pipeline
   - Annotation persistence
   - AI integration (detection, SAM2 tracking)
   - Keyboard shortcuts (hold/toggle modes)
   - Undo/redo system
   - Quality checks
   - Complexity analysis

6. **[06_review_meval_tabs.md](progress/06_review_meval_tabs.md)**
   - ReviewTab (annotation quality checks)
   - MEvalTab (model evaluation)
   - Read-only canvas
   - Overlap detection
   - Frame difference analysis
   - Multi-model comparison
   - Comparison with AnnotationTab

7. **[07_train_capture_tabs.md](progress/07_train_capture_tabs.md)**
   - TrainTab (training workflow)
   - CaptureTab (camera control)
   - Dataset split management
   - Training run wizard
   - Job queue monitoring
   - RealSense integration

## Quick Reference

### System Statistics
- **Architectural Layers**: 14
- **Workspace Tabs**: 6 (Capture, Annotation, Review, MEval, Train, CuteTeleop)
- **Event Types**: 20+
- **Source Files**: ~60+
- **Design Patterns**: 10+

### Key Components

#### Application Level
- **DataLensApplication**: Custom QApplication with event profiling
- **StartupManager**: Coordinates startup stages
- **EventHub**: Central event dispatcher
- **AIModelManager**: Model registry
- **RealSenseDeviceManager**: Device management

#### MainWindow Level
- **PersistenceQueue**: Background saves with debouncing
- **ProjectFileWatcher**: File system monitoring (watchdog/Qt/polling)
- **ProjectCacheManager**: Session-based cache management
- **DatasetSplitService**: Dataset splitting logic
- **TrainingJobManager**: Training job queue
- **TrainingExecutionService**: Training orchestration

#### Tab Level
- **BaseWorkspaceTab**: Base class for all tabs
- **Event subscriptions**: Tab-specific event handling
- **Shortcut management**: Tab-scoped keyboard shortcuts

### Data Flow Patterns

1. **Annotation Save**:
   ```
   User Edit → Cache Update → PersistenceQueue → Debounce → 
   Merge → Snapshot → Worker Thread → Disk Write → Signal
   ```

2. **Media Discovery**:
   ```
   File Created → Watchdog → Qt Thread → FileWatcher → 
   MediaItem → EventHub → Tabs Update
   ```

3. **Training Job**:
   ```
   User Request → Event → JobManager → Queue → 
   ExecutionService → Worker → Progress Events → UI Update
   ```

### Design Patterns Used

1. **Event-Driven Architecture**: EventHub for decoupled communication
2. **Observer Pattern**: File watcher publishes events
3. **Strategy Pattern**: Multiple file watcher backends
4. **Repository Pattern**: JsonProjectRepository
5. **Producer-Consumer**: PersistenceQueue with debouncing
6. **Singleton**: UserStoragePaths, AIModelManager
7. **Template Method**: BaseWorkspaceTab lifecycle
8. **Factory**: Training worker registry
9. **Command Pattern**: Training job queue
10. **State Pattern**: Tab activation/deactivation

## How to Use This Documentation

### For Understanding the Current System
1. Start with **ARCHITECTURE_SUMMARY.md** for the big picture
2. Review **architecture_diagram.md** for visual understanding
3. Dive into specific **progress/** notes for detailed analysis

### For Planning V2
1. Read the "Recommendations for V2" section in **files_checked.md**
2. Review "Future Improvements" in **ARCHITECTURE_SUMMARY.md**
3. Identify bloat and unnecessary complexity in the diagrams
4. Consider which managers/layers are essential vs. optional

### For Development
1. Use **architecture_diagram.md** as a reference
2. Check **files_checked.md** for file locations
3. Review data flow examples for understanding interactions
4. Consult design patterns for consistent implementation

## Key Findings

### Strengths
✅ Clear event-driven architecture
✅ Robust error handling and logging
✅ Non-blocking I/O with background workers
✅ Flexible configuration system
✅ Pluggable tab architecture
✅ Cross-platform support with fallbacks

### Areas for Improvement
⚠️ MainWindow has too many responsibilities
⚠️ Many similar event types could be consolidated
⚠️ Persistence layer could be standardized
⚠️ Some legacy migration code can be removed
⚠️ Service boundaries could be clearer

### Essential Systems for V2
1. **Application Bootstrap** - Keep as-is
2. **Event System** - Keep but simplify
3. **Tab System** - Simplify base class
4. **Persistence** - Standardize interface
5. **Services** - Clarify responsibilities
6. **Preferences** - Keep as-is
7. **Logging** - Keep as-is

### Removable/Optional for V2
1. Legacy migration code
2. Dual file watcher (pick one backend)
3. Redundant state caches
4. Some event type variations

## Mermaid Diagram Highlights

The complete Mermaid diagram in `architecture_diagram.md` shows:

- **All 14 architectural layers** with components
- **Event flow** from publishers to subscribers
- **Data persistence** paths
- **Thread boundaries** (GUI vs. worker threads)
- **Service dependencies**
- **Tab inheritance** hierarchy
- **Storage structure** (filesystem layout)
- **Configuration sources**

## File Organization

```
review_and_plan/
├── README.md                      # This file
├── ARCHITECTURE_SUMMARY.md        # Complete system summary
├── architecture_diagram.md        # Mermaid diagrams
├── files_checked.md              # Progress tracker
└── progress/                     # Detailed analysis
    ├── 01_entry_point.md
    ├── 02_welcome_system.md
    ├── 03_infrastructure_layer.md
    └── 04_services_layer.md
```

## Next Steps

To complete the audit to 100%:

1. **Analyze remaining tab implementations** (detailed)
2. **Document all domain models** (complete)
3. **Analyze training system** (detailed)
4. **Document evaluation system**
5. **Catalog all UI widgets**
6. **Document theme system**
7. **Detail import/export systems**
8. **Complete device management analysis**

## Questions Answered

### What systems run the welcome screen?
- WelcomeWindow (main dialog)
- _UserProfileForm, _ProfileSummary, _ProfileEditDialog (profile)
- _FeatureSelector, _FeatureCard (features)
- _RecentProjectsPanel (projects)
- DependencyInstallThread (async installation)
- Integration with AppPreferences, UserStoragePaths, FeatureDefinition

### What systems run the tabs and UI?
- MainWindow (container)
- QTabWidget (tab container)
- BaseWorkspaceTab (base class)
- 6 tab implementations (Capture, Annotation, Review, MEval, Train, CuteTeleop)
- EventHub (communication)
- Keyboard shortcut management

### What is implemented on a tab-by-tab basis?
- UI layout and widgets
- Event subscriptions (tab-specific)
- Keyboard shortcuts (tab-scoped)
- State persistence (snapshot_state)
- Lifecycle hooks (activate/deactivate)

### What is on an app level?
- EventHub (central dispatcher)
- PersistenceQueue (background saves)
- ProjectFileWatcher (file monitoring)
- ProjectCacheManager (cache management)
- AIModelManager (model registry)
- RealSenseDeviceManager (device management)
- UserStoragePaths (storage management)
- Logging system
- Preferences system
- Theme system

### File writing systems?
- PersistenceQueue (debounced, background, 400ms)
- JsonProjectRepository (synchronous)
- TrainingPersistence (training data)
- Exporters (dataset export)
- Logging (queue-based, rotating files)

### File loading systems?
- JsonProjectRepository (project data)
- Importers (COCO import)
- Preferences loading (JSON)
- UI state loading (JSON)
- Model manifest loading

### File processing systems?
- ProjectFileWatcher (discovery, watchdog/Qt/polling)
- Media indexing (checksums)
- Image processing (PIL)
- Dataset splitting
- Export format conversion

### Signal systems?
- **Qt Signals**: Within-component communication
- **EventHub**: Cross-component communication (20+ event types)
- **Custom Signals**: Tab-specific, dialog-specific, worker-specific

### Manager systems?
- **StartupManager**: Startup coordination
- **EventHub**: Event dispatch
- **AIModelManager**: Model registry
- **RealSenseDeviceManager**: Device management
- **ProjectCacheManager**: Cache management
- **TrainingJobManager**: Training jobs
- **UserStoragePaths**: Storage management (singleton)

### Coordinator systems?
- **MainWindow**: Central coordinator (too much responsibility)
- **TrainingExecutionService**: Training orchestration
- **DatasetSplitService**: Dataset splitting
- **ProjectFileWatcher**: File monitoring coordination

### Keyboard shortcut systems?
- **Global shortcuts**: MainWindow-managed
- **Tab shortcuts**: BaseWorkspaceTab-managed
- **Shortcut modes**: Toggle vs. hold
- **Configuration**: Via preferences
- **Dialog**: KeyboardShortcutsDialog

## Conclusion

This audit provides a comprehensive view of the DataLens architecture, identifying all major systems, managers, coordinators, and data flows. The documentation is structured to support both understanding the current system and planning a V2 redesign with reduced bloat and clearer separation of concerns.

The Mermaid diagram in `architecture_diagram.md` provides a complete visual reference, while the detailed progress notes document specific subsystems. The recommendations in `files_checked.md` and `ARCHITECTURE_SUMMARY.md` provide actionable guidance for V2 development.

---

**Audit Status**: Core + 5/6 tabs complete (~50%)
**Last Updated**: 2024-12-07
**Auditor**: Kiro AI Assistant
