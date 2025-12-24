"""
Pytest configuration for plugin integration tests.

Defines custom command-line options for plugin testing.
"""


def pytest_addoption(parser):
    """Add custom command-line options for plugin testing."""
    parser.addoption(
        "--plugin",
        action="append",
        default=[],
        help="Plugin ID to test (can be specified multiple times). Example: --plugin=capture --plugin=widget_test",
    )
    parser.addoption(
        "--test-all-plugins",
        action="store_true",
        default=False,
        help="Test all available plugins",
    )
    parser.addoption(
        "--generate-inventory",
        action="store_true",
        default=False,
        help="Generate detailed widget inventory report",
    )
