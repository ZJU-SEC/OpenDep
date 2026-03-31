from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from support import PROJECT_ROOT

from adapters import changes_client


class FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class ChangesClientTests(unittest.TestCase):
    def test_build_changes_request_url_uses_last_event_id_and_limit(self) -> None:
        client = changes_client.NpmChangesClient(changes_url="https://replicate.example.test/_changes")

        url = client.build_changes_request_url(since="12345-g1AAAA", limit=500)

        self.assertEqual(url, "https://replicate.example.test/_changes?limit=500&last-event-id=12345-g1AAAA")

    def test_fetch_changes_batch_parses_events_and_last_seq(self) -> None:
        payload = {
            "results": [
                {
                    "seq": "101-g1",
                    "id": "left-pad",
                    "changes": [{"rev": "10-abc"}],
                },
                {
                    "seq": "102-g1",
                    "id": "is-odd",
                    "changes": [{"rev": "11-def"}],
                    "deleted": True,
                },
            ],
            "last_seq": "102-g1",
        }
        client = changes_client.NpmChangesClient(changes_url="https://replicate.example.test/_changes")

        with patch.object(changes_client, "urlopen", return_value=FakeResponse(json.dumps(payload))):
            batch = client.fetch_changes_batch(since="100-g1", limit=2)

        self.assertEqual(batch.last_seq, "102-g1")
        self.assertEqual(batch.source_url, "https://replicate.example.test/_changes?limit=2&last-event-id=100-g1")
        self.assertEqual(len(batch.events), 2)
        self.assertEqual(batch.events[0].package_name, "left-pad")
        self.assertEqual(batch.events[0].changes_rev, "10-abc")
        self.assertFalse(batch.events[0].deleted)
        self.assertTrue(batch.events[1].deleted)


if __name__ == "__main__":
    unittest.main()
