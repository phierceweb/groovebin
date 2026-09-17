"""The stale-bytecode guard: a cache whose code differs from its source goes, a true one stays."""

import importlib.util
import py_compile
import tempfile
import unittest
from pathlib import Path

from _bytecode import purge, stale


class StaleBytecodeTest(unittest.TestCase):
    def test_a_cache_from_another_source_is_removed_and_a_true_one_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "m.py"
            src.write_text("STRIDE = 4\n")
            py_compile.compile(str(src), cfile=importlib.util.cache_from_source(str(src)), doraise=True)
            self.assertIsNone(stale(src))
            stat = src.stat()
            src.write_text("STRIDE = 5\n")                     # same size, the cache's header still matches
            import os
            os.utime(src, (stat.st_atime, stat.st_mtime))
            pyc = stale(src)
            self.assertIsNotNone(pyc)
            self.assertEqual(purge(Path(tmp)), [pyc])
            self.assertFalse(pyc.exists())
            self.assertEqual(purge(Path(tmp)), [])


if __name__ == "__main__":
    unittest.main()
