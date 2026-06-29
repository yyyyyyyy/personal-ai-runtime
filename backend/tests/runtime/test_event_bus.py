"""Tests for Event Bus."""
import asyncio

import pytest

from app.core.runtime.event_bus import EventBus


@pytest.fixture
async def bus():
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.mark.asyncio
async def test_pub_sub(bus):
    received = []

    async def handler(event_type, payload):
        received.append((event_type, payload))

    bus.subscribe("TestEvent", handler)
    bus.publish("TestEvent", {"data": "hello"})
    await asyncio.sleep(0.3)
    assert len(received) == 1
    assert received[0][0] == "TestEvent"
    assert received[0][1]["data"] == "hello"


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    received_a = []
    received_b = []

    async def handler_a(event_type, payload):
        received_a.append(payload)

    async def handler_b(event_type, payload):
        received_b.append(payload)

    bus.subscribe("MultiEvent", handler_a)
    bus.subscribe("MultiEvent", handler_b)
    bus.publish("MultiEvent", {"x": 1})
    await asyncio.sleep(0.3)
    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_unsubscribe(bus):
    received = []

    async def handler(event_type, payload):
        received.append(payload)

    bus.subscribe("RemoveEvent", handler)
    bus.publish("RemoveEvent", {"a": 1})
    await asyncio.sleep(0.2)
    assert len(received) == 1

    bus.unsubscribe("RemoveEvent", handler)
    bus.publish("RemoveEvent", {"a": 2})
    await asyncio.sleep(0.2)
    assert len(received) == 1
