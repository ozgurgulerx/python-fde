import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import coach


class PortalIntegration(unittest.TestCase):
    def test_saved_state_updates_library(self):
        with tempfile.TemporaryDirectory() as root:
            coach.save(root, coach.initial())
            self.assertTrue((Path(root) / "portal/index.html").exists())

    def test_portal_error_does_not_lose_delivery_state(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "portal.build", side_effect=OSError("disk")
        ):
            coach.save(root, {**coach.initial(), "last_sent_at": "confirmed"})
            self.assertEqual(coach.load(root)["last_sent_at"], "confirmed")
            self.assertTrue((Path(root) / "portal-error.json").exists())
