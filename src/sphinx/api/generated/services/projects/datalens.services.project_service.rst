datalens.services.project\_service
==================================

.. automodule:: datalens.services.project_service

   
   .. rubric:: Functions

   .. autosummary::
   
      _require_not_ui_thread
      attach_project
      build_project_meta
      close_project
      close_project_blocking
      decide_core_open_action
      ensure_core_schema
      get_app_context
      get_logger
      inspect_core_db
      load_project
      load_project_async
      migrate_core_schema
      open_connection
      open_project
      open_project_with_plugins
      project_db_path
      project_meta_path
      schedule_project_meta_write
   
   .. rubric:: Classes

   .. autosummary::
   
      ActiveProjectChanged
      AppContext
      EventHub
      Future
      IoWriter
      Path
      ProjectClosed
      ProjectClosing
      ProjectContext
      ProjectOpenFailed
      ProjectOpened
      SqliteProjectDb
   
   .. rubric:: Exceptions

   .. autosummary::
   
      ProjectCloseError
      ProjectOpenError
   