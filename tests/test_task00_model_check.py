import unittest

from src.task00_model_check import StructuredResult, get_temperature


class Task00ModelCheckTests(unittest.TestCase):
    def test_fake_temperature_tool_is_deterministic(self) -> None:
        self.assertEqual(
            get_temperature.invoke({"city": "北京"}),
            "北京: 22°C (模拟数据)",
        )

    def test_structured_result_schema(self) -> None:
        result = StructuredResult(result="ok", confidence=0.9)
        self.assertEqual(result.model_dump(), {"result": "ok", "confidence": 0.9})
