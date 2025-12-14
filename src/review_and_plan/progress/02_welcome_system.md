# Welcome Window System Analysis

## WelcomeWindow (QDialog)
Main dialog for project selection and feature configuration before launching main app.

### Components

#### 1. _UserProfileForm (QGroupBox)
- Collects operator name and email
- Signal: `profileChanged(UserProfile)`
- Fields: name_edit, email_edit
- Validates and normalizes profile data

#### 2. _ProfileSummary (QFrame)
- Compact greeting display once profile is complete
- Signal: `editRequested()`
- Shows "Welcome {name}"
- Edit button to reopen profile form

#### 3. _ProfileEditDialog (QDialog)
- Lightweight dialog for updating stored user profile
- Contains _UserProfileForm
- Save/Cancel buttons
- Validates profile completeness before accepting

#### 4. _FeatureCard (QFrame)
- Individual feature toggle widget
- Signals: `toggled(str, bool)`, `installRequested(str)`
- Shows feature title, description, dependencies
- Install button for missing dependencies
- Highlights missing dependencies in red

#### 5. _FeatureSelector (QGroupBox)
- Container coordinating multiple feature cards
- Signals: `selectionChanged(tuple)`, `installDependenciesRequested(tuple)`
- Grid layout of feature cards (2 columns)
- Tracks feature statuses and dependencies
- Can enable/disable install controls globally

#### 6. _RecentProjectsPanel (QGroupBox)
- Displays recently opened projects
- Signals: `projectChosen(Path, bool)`, `quickLaunch()`
- Buttons: New Project, Open, Open Selected, Continue without project
- Loads recent projects from UI state JSON
- Respects preferences.recent_projects_limit

### Main WelcomeWindow Flow

1. **Initialization**
   - Load preferences and storage
   - Evaluate feature statuses (check dependencies)
   - Create UI with left (projects) and right (profile/features) columns

2. **Profile Management**
   - Stacked layout: ProfileSummary OR ProfileForm
   - Shows form if profile incomplete
   - Shows summary if profile complete
   - Can edit via settings button

3. **Feature Selection**
   - Grid of feature cards
   - Each card shows status, dependencies
   - Can install dependencies per-feature or bulk
   - Uses DependencyInstallThread for async pip install

4. **Dependency Installation**
   - DependencyInstallThread (from ai.install)
   - Signals: started, progress, completed, failed, finished
   - Shows install log in QTextEdit
   - Disables UI during installation
   - Re-evaluates feature status after install

5. **Project Selection**
   - Recent projects list
   - New project (with subproject merge prompt)
   - Open existing project
   - Quick launch (no project)

6. **Launch Decision**
   - Validates: profile complete, features selected, dependencies met
   - Creates LaunchRequest with:
     - project_path
     - create_if_missing flag
     - FeatureSelection (enabled features)
     - merge_subproject_choice (optional)
   - Saves preferences
   - Accepts dialog (returns to app.py)

### Integration Points
- **Preferences**: AppPreferences (user_profile, enabled_features, recent_projects_limit)
- **Storage**: UserStoragePaths (ui_state_file for recent projects)
- **Theme**: AppTheme for consistent styling
- **Domain**: FeatureDefinition, FeatureStatus, LaunchRequest, FeatureSelection
- **AI**: DependencyInstallThread, evaluate_feature_status

### Additional Features
- System report dialog (diagnostics)
- General preferences dialog (from main_window)
- Subproject merge detection and prompt
- Settings icon generation

## Next Steps
- Analyze MainWindow
- Analyze preferences system
- Analyze user storage system
- Analyze domain models
