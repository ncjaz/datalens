# Plugin Widget Testing - Quick Reference

## Most Common Commands

```bash
# Test capture plugin
pytest tests/integration/plugins/test_plugin_widget_groups.py --plugin=capture

# Test multiple plugins
pytest tests/integration/plugins/test_plugin_widget_groups.py --plugin=capture --plugin=widget_test

# Test all plugins
pytest tests/integration/plugins/test_plugin_widget_groups.py --test-all-plugins

# Generate widget inventory
pytest tests/integration/plugins/test_plugin_widget_groups.py --plugin=capture --generate-inventory -v

# Test specific plugin in isolation
pytest tests/integration/plugins/test_plugin_widget_groups.py::test_individual_plugin_widgets[capture]
```

## Command-Line Options

| Option | Description | Example |
|--------|-------------|---------|
| `--plugin=ID` | Test specific plugin (repeatable) | `--plugin=capture --plugin=widget_test` |
| `--test-all-plugins` | Test all available plugins | `--test-all-plugins` |
| `--generate-inventory` | Generate detailed widget report | `--generate-inventory` |

## Available Plugin IDs

- `capture` - Capture plugin (webcams/RealSense)
- `widget_test` - Widget test plugin (UI examples)

## What Gets Tested

✅ Automatic widget discovery
✅ Slider + Auto button interactions
✅ Slider + Reset button functionality
✅ Dropdown + Refresh button operations
✅ Input + Browse button behavior
✅ Plugin enable/disable state management

## See Also

- [PLUGIN_WIDGET_TESTING.md](PLUGIN_WIDGET_TESTING.md) - Full guide
- [WIDGET_GROUP_TESTING.md](WIDGET_GROUP_TESTING.md) - Discovery system
- [KEYBOARD_SHORTCUTS_TESTING.md](KEYBOARD_SHORTCUTS_TESTING.md) - Shortcuts
