"""
Example tests demonstrating how to use EventWatcher and StateWatcher.

These examples show how to test DataLens functionality using the app's
built-in event system and state management, which is the recommended
approach for verifying that actions have their intended effects.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from helpers.workflow_helpers import EventWatcher, StateWatcher, wait_for_condition


@pytest.mark.ui
def test_event_watcher_example(datalens_app):
    """
    Example: Using EventWatcher to verify events are emitted.

    This demonstrates how to:
    1. Create an EventWatcher
    2. Watch for specific events
    3. Perform actions that should emit events
    4. Verify events were received
    5. Clean up event subscriptions
    """
    from datalens.core.context import get_app_context

    app_ctx = get_app_context()

    # Create event watcher
    event_watcher = EventWatcher(app_ctx)

    # Watch for events you expect to be emitted
    # (These are example event names - replace with actual DataLens events)
    event_watcher.watch("example.action_performed")
    event_watcher.watch("example.state_changed")

    try:
        # Perform action that should emit events
        # (This is a placeholder - in real tests, you would click buttons, etc.)

        # Example: Check if event was received (non-blocking)
        if event_watcher.was_received("example.action_performed"):
            print("✓ Event was already received")
        else:
            print("Event not received yet")

        # Example: Wait for event with custom timeout
        success = event_watcher.wait_for("example.state_changed", timeout_ms=1000)
        if success:
            print("✓ Event received within timeout")
            # Get the event data
            event_data = event_watcher.get_event_data("example.state_changed")
            print(f"Event data: {event_data}")

        # Example: Assert event is received (will fail if timeout)
        # event_watcher.assert_received("example.action_performed", timeout_ms=3000)

        print("✓ Event watcher example completed")

    finally:
        # IMPORTANT: Always cleanup to unsubscribe event handlers
        event_watcher.cleanup()


@pytest.mark.ui
def test_state_watcher_example(datalens_app):
    """
    Example: Using StateWatcher to verify state changes.

    This demonstrates how to:
    1. Create a StateWatcher
    2. Get current state snapshot
    3. Perform actions that should change state
    4. Wait for state conditions to become true
    5. Assert state changes occurred
    """
    from datalens.core.context import get_app_context

    app_ctx = get_app_context()

    # Create state watcher
    state_watcher = StateWatcher(app_ctx)

    # Get initial state snapshot
    initial_state = state_watcher.get_snapshot()
    print(f"Initial state: {initial_state}")

    # Example: Check a specific state property
    # (This is a placeholder - replace with actual state properties)
    # if hasattr(initial_state, 'capture'):
    #     print(f"Capture streaming: {initial_state.capture.is_streaming}")

    # Example: Wait for state condition with custom condition function
    # success = state_watcher.wait_for_state(
    #     lambda s: hasattr(s, 'capture') and s.capture.is_streaming,
    #     timeout_ms=3000
    # )
    # if success:
    #     print("✓ State condition met")

    # Example: Assert state condition (will fail if timeout)
    # state_watcher.assert_state(
    #     lambda s: hasattr(s, 'some_property') and s.some_property == expected_value,
    #     timeout_ms=5000,
    #     message="Custom error message if condition not met"
    # )

    # Get updated state
    final_state = state_watcher.get_snapshot()
    print(f"Final state: {final_state}")

    print("✓ State watcher example completed")


@pytest.mark.ui
def test_combined_events_and_state_example(datalens_app):
    """
    Example: Using both EventWatcher and StateWatcher together.

    This is the recommended approach for comprehensive testing:
    1. Watch for events to confirm actions occurred
    2. Monitor state to verify system updated correctly
    3. Check UI to ensure visual feedback matches state
    """
    from datalens.core.context import get_app_context

    app_ctx = get_app_context()

    # Setup watchers
    event_watcher = EventWatcher(app_ctx)
    state_watcher = StateWatcher(app_ctx)

    # Watch for relevant events
    event_watcher.watch("example.started")
    event_watcher.watch("example.completed")

    try:
        # Get initial state
        initial_state = state_watcher.get_snapshot()
        print(f"Initial state: {initial_state}")

        # Perform action (example placeholder)
        # In real test: click_start_button()

        # Verify event was emitted
        # event_watcher.assert_received("example.started", timeout_ms=2000)
        # print("✓ Start event received")

        # Verify state changed
        # state_watcher.assert_state(
        #     lambda s: s.example.is_active,
        #     timeout_ms=1000,
        #     message="State should show active"
        # )
        # print("✓ State confirms active")

        # Verify UI matches state
        # (Check that visual indicators reflect the state)

        print("✓ Combined example completed")

    finally:
        # Cleanup
        event_watcher.cleanup()


@pytest.mark.ui
def test_wait_for_condition_example(datalens_app):
    """
    Example: Using wait_for_condition for custom polling.

    This utility function is useful when you need to wait for:
    - Widget visibility
    - Property changes
    - Custom conditions
    """

    # Example: Wait for a widget to become visible
    # widget = find_some_widget()
    # success = wait_for_condition(
    #     lambda: widget.isVisible(),
    #     timeout_ms=2000
    # )
    # assert success, "Widget should become visible"

    # Example: Wait for a property to change
    # success = wait_for_condition(
    #     lambda: widget.property("state") == "ready",
    #     timeout_ms=3000,
    #     check_interval_ms=50  # Check every 50ms
    # )
    # assert success, "Widget should reach ready state"

    # Example: Wait for a count to increase
    # initial_count = get_frame_count()
    # success = wait_for_condition(
    #     lambda: get_frame_count() > initial_count,
    #     timeout_ms=2000
    # )
    # assert success, "Frame count should increase"

    print("✓ wait_for_condition example completed")


@pytest.mark.ui
def test_visual_indicator_color_change_example(datalens_app):
    """
    Example: Testing visual indicator color changes (red → green).

    This shows how to verify visual feedback like color changes
    in status indicators.
    """

    # Example: Find a status indicator widget
    # indicator = find_widget("stream_status_indicator")

    # Check initial color (red = not streaming)
    # assert "red" in indicator.styleSheet().lower() or \
    #        indicator.property("color") == "red", \
    #        "Initial indicator should be red"
    # print("✓ Initial indicator is red")

    # Perform action that should change color
    # click_start_stream_button()

    # Wait for color to change to green
    # success = wait_for_condition(
    #     lambda: "green" in indicator.styleSheet().lower() or \
    #             indicator.property("color") == "green",
    #     timeout_ms=2000
    # )
    # assert success, "Indicator should turn green when streaming"
    # print("✓ Indicator changed to green")

    # Verify state also confirms streaming
    # from datalens.core.context import get_app_context
    # app_ctx = get_app_context()
    # state = app_ctx.workspace_state.snapshot()
    # assert state.capture.is_streaming, "State should confirm streaming"
    # print("✓ State confirms streaming")

    print("✓ Visual indicator example completed")


# Template for a complete streaming test
@pytest.mark.ui
@pytest.mark.skip(reason="Template - needs actual capture plugin implementation")
def test_camera_streaming_complete_template(datalens_app):
    """
    Template: Complete camera streaming test using events, state, and UI checks.

    This is a TEMPLATE showing how to write a comprehensive test.
    Replace the TODOs with actual implementation for your capture plugin.
    """
    from datalens.core.context import get_app_context

    app_ctx = get_app_context()

    # Setup watchers
    event_watcher = EventWatcher(app_ctx)
    state_watcher = StateWatcher(app_ctx)

    # TODO: Replace with actual event names from your capture plugin
    event_watcher.watch("capture.streaming_started")
    event_watcher.watch("capture.frame_received")
    event_watcher.watch("capture.streaming_stopped")

    try:
        # Verify initial state
        initial_state = state_watcher.get_snapshot()
        # TODO: Add actual state property check
        # assert not initial_state.capture.is_streaming, "Should not be streaming"

        # TODO: Find and click start button
        # start_button = find_start_stream_button()
        # QTest.mouseClick(start_button, Qt.LeftButton)

        # Wait for streaming_started event
        event_watcher.assert_received("capture.streaming_started", timeout_ms=3000)
        print("✓ streaming_started event received")

        # Verify state changed
        state_watcher.assert_state(
            lambda s: s.capture.is_streaming,  # TODO: Adjust to actual state property
            timeout_ms=1000,
            message="State should indicate streaming",
        )
        print("✓ State confirms streaming")

        # Wait for frame data
        event_watcher.assert_received("capture.frame_received", timeout_ms=2000)
        print("✓ Frame data received")

        # Verify frame count is increasing
        initial_frame_count = state_watcher.get_snapshot().capture.frame_count
        QTest.qWait(500)
        current_frame_count = state_watcher.get_snapshot().capture.frame_count
        assert current_frame_count > initial_frame_count, "Frame count should increase"
        print(f"✓ Frames streaming ({current_frame_count} frames)")

        # TODO: Verify UI indicator changed to green
        # indicator = find_stream_indicator()
        # assert "green" in indicator.styleSheet().lower(), "Indicator should be green"

        # Stop streaming
        # TODO: Click stop button
        # QTest.mouseClick(start_button, Qt.LeftButton)

        # Wait for streaming_stopped event
        event_watcher.assert_received("capture.streaming_stopped", timeout_ms=2000)
        print("✓ streaming_stopped event received")

        # Verify state updated
        state_watcher.assert_state(
            lambda s: not s.capture.is_streaming, timeout_ms=1000, message="Should stop streaming"
        )
        print("✓ State confirms stopped")

        print("\n✅ Complete streaming test passed!")

    finally:
        event_watcher.cleanup()
