# Entry Point Analysis

## Main Application Flow (app.py)

### DataLensApplication (QApplication subclass)
- Custom QApplication with event profiling
- Logs slow UI events (threshold: 75ms default)
- Crash handling for unhandled Qt events
- Environment variable: `DATALENS_SLOW_EVENT_THRESHOLD_MS`

### Startup Sequence
1. **Argument Parsing**
   - `--skip-welcome`: Bypass welcome window
   - `--load-last-project`: Auto-load recent project

2. **Initialization**
   - Configure logging (via `logging_config`)
   - Install crash handlers
   - Load persisted theme
   - Create `StartupDialog` (progress indicator)

3. **Startup Manager**
   - Coordinates startup stages
   - Shows progress in dialog
   - Stages: "Preparing tools", "Loading preferences", "Creating main window"

4. **Launch Path Decision**
   - **Skip Welcome**: Restore previous session from UI state
   - **Show Welcome**: Display `WelcomeWindow` for project selection

5. **Main Window Creation**
   - Create `MainWindow` with theme, preferences, launch_request
   - Show window and enter Qt event loop

## Key Dependencies Identified
- `startup_dialog.StartupDialog` - Progress UI
- `startup_manager.StartupManager` - Startup coordination
- `ui.launcher.WelcomeWindow` - Project selection
- `ui.main_window.MainWindow` - Main application window
- `preferences` - User preferences system
- `user_storage` - User data storage
- `theme` - Theme management
- `domain.startup` - Launch request models
- `domain.features` - Feature flags

## Next Steps
- Analyze StartupManager
- Analyze WelcomeWindow
- Analyze MainWindow
- Analyze preferences system
- Analyze user storage
