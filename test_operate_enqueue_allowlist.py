import os
import unittest
from unittest.mock import patch

from server import operate_enqueue_functions


class OperateEnqueueAllowlistTest(unittest.TestCase):
    def test_empty_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(operate_enqueue_functions(), set())

    def test_parses_exact_function_names(self):
        with patch.dict(
            os.environ,
            {"RQDB4AI_OPERATE_ENQUEUE_FUNCTIONS": "app.jobs.run, other.task  ,app.jobs.run"},
            clear=True,
        ):
            self.assertEqual(operate_enqueue_functions(), {"app.jobs.run", "other.task"})


if __name__ == "__main__":
    unittest.main()
