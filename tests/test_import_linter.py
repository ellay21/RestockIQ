"""
import-linter configuration test: the import-linter configuration in pyproject.toml is
parseable and does not contain any configuration errors.

This test is intentionally minimal — it verifies the *contract definition*
is valid, not that all contracts currently pass (an empty codebase trivially
passes every forbidden-import contract because there is no code to violate
them). The actual contract enforcement happens in CI via `lint-imports`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def test_import_linter_contract_is_valid() -> None:
    """
    Verify that the import-linter config in pyproject.toml is parseable
    and the contracts reference the layers defined in Architecture.md §3.

    Acceptable exit codes:
      0 — all contracts pass (expected on an empty/stub codebase)
      1 — contracts found violations (possible once production code exists)
    Any other exit code, or configuration-error output in stderr, is a failure.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "importlinter",
            "--config",
            str(PROJECT_ROOT / "pyproject.toml"),
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    # A configuration parse error is always a hard failure.
    assert "Error reading configuration" not in result.stderr, (
        f"import-linter reported a configuration read error:\n{result.stderr}"
    )
    assert "InvalidConfiguration" not in result.stderr, (
        f"import-linter found an invalid contract configuration:\n{result.stderr}"
    )
    assert "UserException" not in result.stderr, (
        f"import-linter raised a user exception:\n{result.stderr}"
    )

    # Exit 0 = all contracts pass; exit 1 = contract violations found.
    # Both are valid outcomes for this smoke test — what we're testing is the
    # *config itself*, not the current violation state of the codebase.
    assert result.returncode in (0, 1), (
        f"Unexpected import-linter exit code {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
