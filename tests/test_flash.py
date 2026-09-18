import contextlib
import hashlib
import io
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import yaml
from tooling.flash import flash_node as flash


class FlashTests(unittest.TestCase):
    def test_corrupt_cache_never_reaches_esptool(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(flash, "CACHE", pathlib.Path(directory)):
            digest = hashlib.sha256(b"valid").hexdigest()
            path = pathlib.Path(directory) / digest[:16] / "image.bin"
            path.parent.mkdir()
            path.write_bytes(b"corrupt")
            with self.assertRaises(SystemExit), patch.object(flash.urllib.request, "urlretrieve") as download:
                flash.fetch("https://example.org/image.bin", digest)
            download.assert_not_called()
            self.assertFalse(path.exists())

    def test_download_only_verifies_four_images_without_serial(self):
        with patch.object(flash, "fetch", return_value=pathlib.Path("image.bin")) as fetch, patch.object(flash.subprocess, "run") as run:
            with contextlib.redirect_stdout(io.StringIO()):
                flash.main(["--download-only"])
            self.assertEqual(fetch.call_count, 4)
            run.assert_not_called()

    def test_lock_offsets_cover_bootloader_partition_otadata_app(self):
        lock = yaml.safe_load((flash.HERE / "firmware.lock").read_text())
        target = lock["targets"]["atoms3-lite"]
        self.assertEqual({p["name"]: int(p["offset"], 0) for p in target["parts"]},
                         {"bootloader": 0, "partitions": 0x8000, "boot_app0": 0xe000, "app": 0x10000})
        for part in target["parts"]:
            self.assertNotIn("/main/", part["url"])
            self.assertRegex(part["sha256"], "^[a-f0-9]{64}$")

    def test_flash_requires_port_and_rejects_invalid_baud_before_download(self):
        for args in ([], ["--port", "COM1", "--baud", "0"]):
            with self.subTest(args=args), patch.object(flash, "fetch") as fetch:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    flash.main(args)
                fetch.assert_not_called()
