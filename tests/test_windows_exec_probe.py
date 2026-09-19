"""Exercise actual Windows PowerShell/native argument boundaries, not a Codex host."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == "nt", "requires the Windows native argument ABI")
class WindowsExecProbeTests(unittest.TestCase):
    def test_file_arguments_utf8_and_nonzero_exit_are_preserved(self):
        pwsh = shutil.which("pwsh")
        self.assertIsNotNone(pwsh, "PowerShell 7 is required for this Windows test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "中文 路径 ' [参数]"
            root.mkdir()
            child = root / "argument probe.py"
            runner = root / "runner.ps1"
            parser = root / "parse.ps1"
            data = root / "input.json"
            report = root / "report.json"
            values = ["", 'double " quote', "single ' quote", "$name", "`tick",
                      "slash\\", "&", "|", "中文", "first\nsecond\nthird",
                      json.dumps({"quoted": 'a"b', "empty": "", "path": str(root)}, ensure_ascii=False)]
            child.write_text(
                "import json,sys\nprint(json.dumps(sys.argv[1:], ensure_ascii=False))\nsys.exit(37)\n",
                encoding="utf-8",
            )
            data.write_text(json.dumps({"arguments": values}, ensure_ascii=False), encoding="utf-8")
            runner.write_text('''param(
    [string]$PythonExe, [string]$ProbePath,
    [string]$DataPath, [string]$ReportPath
)
$ErrorActionPreference = 'Stop'
$payload = Get-Content -LiteralPath $DataPath -Raw -Encoding UTF8 | ConvertFrom-Json
$argList = @($ProbePath) + @($payload.arguments)
$output = & $PythonExe @argList
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 37) { throw "Expected exit 37, got $nativeExit" }
[IO.File]::WriteAllText($ReportPath, ($output -join [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
Write-Output "native_exit=$nativeExit"
exit 0
''', encoding="utf-8")
            parser.write_text('''param([string]$RunnerPath)
$tokens = $null
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($RunnerPath, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { $errors | Write-Error; exit 1 }
exit 0
''', encoding="utf-8")
            env = dict(os.environ, PYTHONUTF8="1")
            options = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=30)
            preflight = subprocess.run([pwsh, "-NoLogo", "-NoProfile", "-NonInteractive",
                                        "-File", str(parser), "-RunnerPath", str(runner)], **options)
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            run = subprocess.run([pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(runner),
                                  "-PythonExe", sys.executable, "-ProbePath", str(child),
                                  "-DataPath", str(data), "-ReportPath", str(report)], **options)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("native_exit=37", run.stdout)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")), values)


if __name__ == "__main__":
    unittest.main()
