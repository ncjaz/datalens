# Plugin Plans (V2)

This folder contains **implementation plans** for the first "real" V2 plugins and their shared subsystems.

- `Capture.md` - Camera capture workspace (RealSense + webcams) + sharing contracts.
- `canvas_system.md` - Reusable image+overlay canvas system (V1-style) for plugins.

Related core plans that these plugins depend on:

- `datalens/src/review_and_plan/media_index.md` - Core-owned media/file index (so plugins can reference project files without rescanning or DB poking).
