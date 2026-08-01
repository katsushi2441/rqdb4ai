import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import server


class FakeJob:
    id = "job-image"
    result = {"ok": True, "image_base64": "x" * 3000}

    def get_status(self, refresh=False):
        return "finished"


class JobResultApiTest(unittest.TestCase):
    def test_returns_full_result_beyond_dashboard_preview(self):
        with patch.dict(os.environ, {"RQDB4AI_API_TOKEN": "test-token"}, clear=True), patch.object(
            server, "fetch_job", return_value=FakeJob()
        ):
            response = TestClient(server.app).get(
                "/api/jobs/job-image/result",
                headers={"Authorization": "Bearer test-token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["result"]["image_base64"]), 3000)

    def test_requires_authentication(self):
        with patch.dict(os.environ, {"RQDB4AI_API_TOKEN": "test-token"}, clear=True):
            response = TestClient(server.app).get("/api/jobs/job-image/result")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
