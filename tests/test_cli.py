import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from rtl_intel.cli import main


class CliTests(unittest.TestCase):
    def test_json_output_is_machine_readable(self):
        source = "module passthrough(input wire a, output wire y); assign y = a; endmodule\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pass.v"
            path.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main([str(path), "--format", "json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, status)
        self.assertEqual("rtl-intel", payload["tool"]["name"])
        self.assertEqual(1, payload["summary"]["modules_found"])
        self.assertIn("design_summary", payload)

    def test_fail_on_error_sets_nonzero_status(self):
        source = "module bad(output logic y); endmodule\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.sv"
            path.write_text(source, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                status = main([str(path), "--fail-on", "error"])

        self.assertEqual(1, status)


if __name__ == "__main__":
    unittest.main()

