import unittest

from datalens.core.events import EventHub
from datalens.domain.plugin import PluginId
from datalens.domain.plugin.preferences_schema import PluginPreferencesSchema
from datalens.domain.system.settings import AppSettings
from datalens.services.plugin_preferences_service import PluginPreferencesService


class _DummyWriter:
    def __init__(self) -> None:
        self.saved: list[AppSettings] = []

    def request_save(self, settings: AppSettings) -> None:
        self.saved.append(settings)


class PluginPreferencesServiceTests(unittest.TestCase):
    def test_set_publishes_event_and_requests_save(self) -> None:
        hub = EventHub()
        hub.attach_ui_scheduler(lambda fn: fn())

        schema = PluginPreferencesSchema.from_dict(
            {
                "schema_version": 1,
                "sections": [
                    {
                        "id": "devices",
                        "title": "Devices",
                        "fields": [
                            {
                                "key": "scan_mode",
                                "title": "Scan Mode",
                                "kind": "toggle",
                                "options": [
                                    {"id": "manual", "label": "Manual"},
                                    {"id": "auto", "label": "Auto"},
                                ],
                                "default": "manual",
                            }
                        ],
                    }
                ],
            }
        )

        writer = _DummyWriter()
        svc = PluginPreferencesService(events=hub, writer=writer, schema_resolver=lambda pid: schema)
        svc.apply_settings(AppSettings())

        plugin_id = PluginId("capture")
        events: list[set[str]] = []
        unsubscribe = svc.subscribe(plugin_id, lambda _pid, keys: events.append(set(keys)))
        try:
            svc.set(plugin_id, "scan_mode", "auto")
        finally:
            unsubscribe()

        self.assertEqual(len(writer.saved), 1)
        self.assertEqual(events, [{"scan_mode"}])
        snap = svc.snapshot()
        self.assertEqual(snap["plugins"]["capture"]["scan_mode"], "auto")


if __name__ == "__main__":
    unittest.main()

