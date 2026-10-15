"""No third-party dependencies. Never installs into the user's package root."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from package import FILES, build


class Package(unittest.TestCase):
    def test_reproducible_archive_and_checksum(self):
        with tempfile.TemporaryDirectory(prefix="neon-package-test-") as temp:
            first = build(Path(temp) / "first")
            second = build(Path(temp) / "second")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            checksum = hashlib.sha256(first.read_bytes()).hexdigest()
            self.assertEqual((first.parent / "SHA256SUMS").read_text(),
                             f"{checksum}  {first.name}\n")
            with tarfile.open(first) as tar:
                self.assertEqual(set(tar.getnames()), set(FILES))
                for entry in tar.getmembers():
                    self.assertTrue(entry.isfile())
                    self.assertEqual(entry.mtime, 0)
                    self.assertEqual(tar.extractfile(entry).read(), FILES[entry.name].read_bytes())

    @unittest.skipUnless(shutil.which("kpackagetool6"), "Optional: kpackagetool6 not installed")
    def test_isolated_install_upgrade_and_remove(self):
        with tempfile.TemporaryDirectory(prefix="neon-kpackage-test-") as temp:
            root = Path(temp)
            archive = build(root / "dist")
            env = os.environ.copy()
            for variable, folder in (("XDG_DATA_HOME", "data"),
                                     ("XDG_CONFIG_HOME", "config"),
                                     ("XDG_CACHE_HOME", "cache")):
                env[variable] = str(root / folder)
            env["QT_QPA_PLATFORM"] = "offscreen"
            package_root = root / "data/kwin/effects"
            command = ["kpackagetool6", "--type", "KWin/Effect",
                       "--packageroot", str(package_root)]

            def run(*arguments):
                result = subprocess.run(command + list(arguments), env=env,
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            run("--install", str(archive))
            installed = package_root / "neon-digital-minimize"
            for name, source in FILES.items():
                self.assertEqual((installed / name).read_bytes(), source.read_bytes())
            self.assertIn("Neon Circuit Digital Transit", run("--show", "neon-digital-minimize"))
            # KPackage may refuse a same-version upgrade; exercise a temporary next version.
            with tarfile.open(archive) as tar:
                staging = root / "upgrade"
                tar.extractall(staging, filter="data")
            metadata_path = staging / "metadata.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["KPlugin"]["Version"] = "0.1.1"
            metadata_path.write_text(json.dumps(metadata))
            run("--upgrade", str(staging))
            self.assertEqual(json.loads((installed / "metadata.json").read_text())["KPlugin"]["Version"],
                             "0.1.1")
            run("--remove", "neon-digital-minimize")
            self.assertFalse(installed.exists())


if __name__ == "__main__":
    unittest.main()
