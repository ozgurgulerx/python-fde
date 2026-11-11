import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import public_refs  # noqa: F401
import coach


class GenerationSchemaTests(unittest.TestCase):
    def test_generated_schema_requires_every_property_but_legacy_packet_stays_valid(
        self,
    ):
        client = Mock()
        with patch.object(coach, "client", return_value=client):
            coach.generate("/unused", coach.initial())
        schema = client.call.call_args.args[2]
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        packet = json.loads((coach.SKILL / "references/first.json").read_text())
        packet.pop("source_question_id", None)
        self.assertEqual(coach.validate_packet(packet), packet)


if __name__ == "__main__":
    unittest.main()
