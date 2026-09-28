"""Exercise the installer's actual private-config gate without a VPS."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


INSTALLER = Path(__file__).resolve().parents[1] / "deploy" / "vps" / "install.sh"
TEMPLATE = Path(__file__).resolve().parents[1] / "deploy" / "vps" / "frps.toml.template"
LISTENER_CHECK = Path(__file__).resolve().parents[1] / "deploy" / "vps" / "check-listeners.py"


class PrivateConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = INSTALLER.read_text(encoding="utf-8")
        opening = "python3 - \"$private_config\" <<'PY'"
        cls.validator = script.split(opening, 1)[1].split("\n", 1)[1].split("\nPY\n", 1)[0]
        cls.valid = TEMPLATE.read_text(encoding="utf-8").replace(
            "REPLACE_WITH_RANDOM_TOKEN", "A" * 43
        )

    def check_config(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frps.toml"
            path.write_text(content, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-", str(path)],
                input=self.validator,
                text=True,
                capture_output=True,
            ).returncode

    def test_valid_template_and_reordered_fields(self):
        self.assertEqual(0, self.check_config(self.valid))
        lines = [line for line in self.valid.splitlines() if not line.startswith("#")]
        self.assertEqual(0, self.check_config("\n".join(reversed(lines))))

    def test_rejects_public_proxy_and_extra_config(self):
        self.assertNotEqual(
            0,
            self.check_config(self.valid.replace('"127.0.0.1"', '"0.0.0.0"')),
        )
        self.assertNotEqual(0, self.check_config(self.valid + "\nwebServer.port = 7500\n"))
        self.assertNotEqual(0, self.check_config(self.valid.replace("8072", "8071")))
        self.assertNotEqual(0, self.check_config(self.valid.replace("8083", "8084")))

    def test_rejects_placeholder_and_weak_token(self):
        self.assertNotEqual(0, self.check_config(TEMPLATE.read_text(encoding="utf-8")))
        self.assertNotEqual(0, self.check_config(self.valid.replace("A" * 43, "short")))


class ListenerTests(unittest.TestCase):
    def check_listeners(self, kind, output):
        return subprocess.run(
            [sys.executable, str(LISTENER_CHECK), kind],
            input=output,
            text=True,
            capture_output=True,
        ).returncode

    def test_control_accepts_public_wildcard_forms(self):
        for address in ("*:8072", "0.0.0.0:8072", "[::]:8072"):
            with self.subTest(address=address):
                output = f"LISTEN 0 4096 {address} *:*\n"
                self.assertEqual(0, self.check_listeners("control", output))

    def test_control_requires_expected_listener(self):
        self.assertNotEqual(0, self.check_listeners("control", ""))
        self.assertNotEqual(0, self.check_listeners("control", "LISTEN 0 4096 127.0.0.1:8072 *:*\n"))
        self.assertNotEqual(0, self.check_listeners("control", "LISTEN 0 4096 *:8071 *:*\n"))

    def test_proxy_allows_absent_or_loopback_only(self):
        self.assertEqual(0, self.check_listeners("proxy", ""))
        self.assertEqual(0, self.check_listeners("proxy", "LISTEN 0 4096 127.0.0.1:8083 *:*\n"))
        for address in ("*:8083", "0.0.0.0:8083", "[::]:8083", "[::1]:8083"):
            with self.subTest(address=address):
                self.assertNotEqual(
                    0, self.check_listeners("proxy", f"LISTEN 0 4096 {address} *:*\n")
                )


if __name__ == "__main__":
    unittest.main()
