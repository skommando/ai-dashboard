"""Linux must not enter the Windows Job Object supervisor and leave orphans."""
from contextlib import redirect_stderr
import io
import unittest
from unittest import mock
from scripts import service


class PlatformTests(unittest.TestCase):
    def test_non_windows_refuses_before_reading_configuration_or_spawning(self):
        output = io.StringIO()
        with mock.patch.object(service.os, "name", "posix"), \
             mock.patch.object(service, "load_config") as load_config, \
             mock.patch.object(service, "supervise") as supervise, \
             redirect_stderr(output):
            self.assertEqual(service.main(), 2)
        self.assertIn("systemd", output.getvalue())
        load_config.assert_not_called()
        supervise.assert_not_called()
