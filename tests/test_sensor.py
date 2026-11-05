"""Offline regression tests for the legacy YAML ING Stocks sensor."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Lightweight Home Assistant stubs: tests do not require a running HA instance.
ha = types.ModuleType("homeassistant")
ha.__path__ = []
helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
entity_mod = types.ModuleType("homeassistant.helpers.entity")
entity_mod.Entity = type("Entity", (), {})
client_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
client_mod.async_get_clientsession = lambda hass: hass.session
sys.modules.update({
    "homeassistant": ha,
    "homeassistant.helpers": helpers,
    "homeassistant.helpers.entity": entity_mod,
    "homeassistant.helpers.aiohttp_client": client_mod,
})
path = Path(__file__).resolve().parents[1] / "custom_components/ingstocks/sensor.py"
spec = importlib.util.spec_from_file_location("ingstocks_sensor_under_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.error:
            raise self.error

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return next(self.responses)


class SensorTests(unittest.TestCase):
    def test_success_and_community_api_paths(self):
        session = FakeSession([
            FakeResponse({"price": 123.456, "name": "ETF", "changePercent": 1.5}),
            FakeResponse({"dividendYield": 0.0234, "fiftyTwoWeekLow": 99}),
        ])
        sensor = module.INGStocksSensor("DE0000000001", session)
        asyncio.run(sensor.async_update())
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.state, 123.46)
        self.assertEqual(sensor.extra_state_attributes["change_percent"], 1.5)
        self.assertEqual(sensor.extra_state_attributes["52w_low"], 99)
        self.assertIn("/api/v1/instrument-header?isinOrSearchTerm=DE0000000001", session.urls[0])
        self.assertIn("/api/v1/share/keyfigures/DE0000000001", session.urls[1])

    def test_missing_price_marks_unavailable(self):
        session = FakeSession([FakeResponse({"name": "ETF"})])
        sensor = module.INGStocksSensor("DE0000000001", session)
        asyncio.run(sensor.async_update())
        self.assertFalse(sensor.available)

    def test_http_error_marks_unavailable_and_preserves_last_value(self):
        import aiohttp
        session = FakeSession([
            FakeResponse({"price": 42}), FakeResponse({}),
            FakeResponse(error=aiohttp.ClientResponseError(None, (), status=503)),
        ])
        sensor = module.INGStocksSensor("DE0000000001", session)
        asyncio.run(sensor.async_update())
        self.assertEqual(sensor.state, 42)
        asyncio.run(sensor.async_update())
        self.assertFalse(sensor.available)
        self.assertEqual(sensor.state, 42)

    def test_unexpected_payload_marks_unavailable(self):
        sensor = module.INGStocksSensor("DE0000000001", FakeSession([FakeResponse([])]))
        asyncio.run(sensor.async_update())
        self.assertFalse(sensor.available)


if __name__ == "__main__":
    unittest.main()
