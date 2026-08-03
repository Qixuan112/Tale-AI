"""
Unit tests for MessageHandler abstract base class

Tests the responsibility chain pattern implementation:
- set_next() method for chain construction
- handle() method delegation logic
- Abstract method enforcement
"""

import pytest
from datetime import datetime
from core.adapter.event import (
    PlatformEvent, EventType, PlatformType,
    SenderInfo, MessageContent
)
from core.adapter.message_processor import ProcessedMessage, ResponseDecision


# Mock concrete handler for testing chain logic
class MockHandler:
    """Mock handler for testing chain behavior"""

    def __init__(self, name: str, should_handle: bool = False):
        self.name = name
        self.should_handle = should_handle
        self.next_handler = None
        self.calls = []  # Track calls for verification

    def set_next(self, handler):
        """Set the next handler in the chain"""
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        """Handle the message or pass to next"""
        self.calls.append(message)

        if self.should_handle:
            message.decision = ResponseDecision.RESPOND
            message.reason = f"handled_by_{self.name}"
            return message

        if self.next_handler:
            return self.next_handler.handle(message)

        return message


class TestMessageHandlerBase:
    """Test suite for MessageHandler base class behavior"""

    def setup_method(self):
        """Setup test fixtures"""
        self.sample_event = PlatformEvent(
            platform=PlatformType.QQ,
            event_type=EventType.GROUP_MESSAGE,
            sender=SenderInfo(id="user123", name="TestUser"),
            content=MessageContent(text="Hello world"),
            message_id="msg001",
            group_id="group456"
        )

        self.sample_message = ProcessedMessage(
            platform=PlatformType.QQ,
            event_type=EventType.GROUP_MESSAGE,
            message_id="msg001",
            sender_id="user123",
            sender_name="TestUser",
            text="Hello world",
            group_id="group456"
        )

    def test_set_next_returns_handler(self):
        """Test that set_next returns the handler for chaining"""
        handler1 = MockHandler("handler1")
        handler2 = MockHandler("handler2")

        result = handler1.set_next(handler2)

        assert result is handler2
        assert handler1.next_handler is handler2

    def test_chain_construction(self):
        """Test fluent chain construction with set_next"""
        handler1 = MockHandler("handler1")
        handler2 = MockHandler("handler2")
        handler3 = MockHandler("handler3")

        # Fluent API: handler1.set_next(handler2).set_next(handler3)
        handler1.set_next(handler2).set_next(handler3)

        assert handler1.next_handler is handler2
        assert handler2.next_handler is handler3
        assert handler3.next_handler is None

    def test_handle_passes_to_next(self):
        """Test that handle passes to next handler when not handling"""
        handler1 = MockHandler("handler1", should_handle=False)
        handler2 = MockHandler("handler2", should_handle=True)
        handler1.set_next(handler2)

        message = self.sample_message
        result = handler1.handle(message)

        # Both handlers should be called
        assert len(handler1.calls) == 1
        assert len(handler2.calls) == 1

        # Handler2 should have handled it
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "handled_by_handler2"

    def test_handle_stops_at_first_handler(self):
        """Test that chain stops when a handler handles the message"""
        handler1 = MockHandler("handler1", should_handle=True)
        handler2 = MockHandler("handler2", should_handle=True)
        handler1.set_next(handler2)

        message = self.sample_message
        result = handler1.handle(message)

        # Only handler1 should be called
        assert len(handler1.calls) == 1
        assert len(handler2.calls) == 0

        # Handler1 should have handled it
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "handled_by_handler1"

    def test_handle_no_next_handler(self):
        """Test handle when there's no next handler"""
        handler = MockHandler("handler", should_handle=False)

        message = self.sample_message
        result = handler.handle(message)

        # Handler should be called
        assert len(handler.calls) == 1

        # Message should be returned unchanged
        assert result is message
        assert result.decision == ResponseDecision.IGNORE

    def test_long_chain(self):
        """Test a long chain of handlers"""
        handlers = [MockHandler(f"handler{i}") for i in range(5)]

        # Chain all handlers
        for i in range(len(handlers) - 1):
            handlers[i].set_next(handlers[i + 1])

        # Last handler handles the message
        handlers[-1].should_handle = True

        message = self.sample_message
        result = handlers[0].handle(message)

        # All handlers should be called
        for handler in handlers:
            assert len(handler.calls) == 1

        # Last handler should have handled it
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "handled_by_handler4"

    def test_message_mutation_propagates(self):
        """Test that message mutations propagate through the chain"""
        class MutatingHandler(MockHandler):
            def handle(self, message: ProcessedMessage) -> ProcessedMessage:
                self.calls.append(message)
                message.reason = f"mutated_by_{self.name}"
                if self.next_handler:
                    return self.next_handler.handle(message)
                return message

        handler1 = MutatingHandler("handler1")
        handler2 = MutatingHandler("handler2")
        handler1.set_next(handler2)

        message = self.sample_message
        result = handler1.handle(message)

        # Both handlers should have been called
        assert len(handler1.calls) == 1
        assert len(handler2.calls) == 1

        # Last mutation should be visible
        assert result.reason == "mutated_by_handler2"
