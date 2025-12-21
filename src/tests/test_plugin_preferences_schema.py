import unittest

from datalens.domain.plugin.preferences_schema import PluginPreferencesSchema, PreferenceField, PreferenceKind


class PluginPreferencesSchemaTests(unittest.TestCase):
    def test_schema_version_is_accepted(self) -> None:
        schema = PluginPreferencesSchema.from_dict(
            {
                "schema_version": 2,
                "sections": [
                    {
                        "id": "s",
                        "title": "S",
                        "fields": [
                            {
                                "key": "k",
                                "title": "K",
                                "kind": "string",
                                "default": "x",
                            }
                        ],
                    }
                ],
            }
        )
        self.assertEqual(schema.version, 2)
        dumped = schema.to_dict()
        self.assertEqual(dumped["schema_version"], 2)

    def test_version_alias_is_accepted(self) -> None:
        schema = PluginPreferencesSchema.from_dict({"version": 3, "sections": []})
        self.assertEqual(schema.version, 3)

    def test_toggle_requires_exactly_two_options(self) -> None:
        with self.assertRaises(ValueError):
            PreferenceField.from_dict(
                {
                    "key": "scan_mode",
                    "title": "Scan Mode",
                    "kind": PreferenceKind.TOGGLE.value,
                    "options": [{"id": "manual", "label": "Manual"}],
                    "default": "manual",
                }
            )

