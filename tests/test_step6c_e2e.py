
import os
import sys
import unittest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from pdd.fix_code_loop import fix_code_loop
from pdd.sync_determine_operation import get_meta_dir
import pdd

class TestStep6cE2E(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path("temp_e2e_test")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Setup for fix_code_loop test
        self.code_file = self.temp_dir / "my_code.py"
        self.code_file.write_text("def add(a, b): return a - b") # Incorrect
        
        self.verification_program = self.temp_dir / "verify.py"
        self.verification_program.write_text("from my_code import add\nassert add(1, 2) == 3\n")
        
        self.error_log = self.temp_dir / "errors.log"
        self.prompt_file = self.temp_dir / "my_prompt.prompt"
        self.prompt_file.write_text("Write a function that adds two numbers.")

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("pdd.fix_code_loop.fix_code_module_errors")
    def test_fix_code_loop_integration(self, mock_fix):
        """E2E test for fix_code_loop integrating with fix_code_module_errors."""
        # Mock fix_code_module_errors to return a "fixed" version
        # Signature: (update_program, update_code, fixed_program, fixed_code, program_code_fix, total_cost, model_name)
        mock_fix.return_value = (
            True, True, "from my_code import add\nassert add(1, 2) == 3\n", 
            "def add(a, b): return a + b", "fix desc", 0.1, "gpt-4"
        )

        # We need to ensure the local environment can import the temp code file
        # Add temp_dir to sys.path for the current process
        sys.path.insert(0, str(self.temp_dir))
        # AND set PYTHONPATH for the subprocesses called by fix_code_loop
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.temp_dir.resolve()) + os.pathsep + env.get("PYTHONPATH", "")
        
        try:
            with patch.dict(os.environ, env):
                # We need max_attempts >= 2 because fix_code_loop verifies *before* fixing, 
                # and only verifies the fix in the *next* iteration.
                success, final_prog, final_code, attempts, cost, model = fix_code_loop(
                    code_file=str(self.code_file),
                    prompt="Add numbers",
                    verification_program=str(self.verification_program),
                    strength=0.5,
                    temperature=0.0,
                    max_attempts=2,
                    budget=10.0,
                    error_log_file=str(self.error_log),
                    prompt_file=str(self.prompt_file),
                    agentic_fallback=False
                )
            
            self.assertTrue(success, "fix_code_loop should succeed with mocked fix")
            self.assertIn("a + b", final_code)
            self.assertEqual(attempts, 1) # It should succeed on the 2nd verification (after 1 fix)
            self.assertEqual(cost, 0.1)
        finally:
            sys.path.pop(0)

    def test_sync_meta_dir_resolution_integration(self):
        """E2E test for sync meta dir resolution across modules."""
        # Create a nested structure:
        # root/
        #   .pddrc
        #   subdir/
        #     target.py
        
        root = (self.temp_dir / "project_root").resolve()
        root.mkdir()
        (root / ".pddrc").write_text("project_name: test_project")
        
        subdir = root / "subdir"
        subdir.mkdir()
        target = subdir / "target.py"
        target.touch()
        
        # Test finding .pddrc from subdir
        # get_meta_dir(project_root=None, paths=None)
        # paths must be a dict
        meta_dir = get_meta_dir(paths={"code": str(target)})
        self.assertEqual(meta_dir.resolve(), root / ".pdd" / "meta")

    def test_pdd_package_exports_integration(self):
        """Verify pdd package correctly exports and provides functioning utilities."""
        report_text = "Analysis <step_report>SUCCESS: All tests passed</step_report> more text"
        report = pdd.extract_step_report(report_text)
        self.assertEqual(report, "SUCCESS: All tests passed")

    def test_dependency_integrity_integration(self):
        """Verify that dependencies are correctly segregated in pyproject.toml."""
        import tomllib
        pyproject_path = project_root / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        
        main_deps = data.get("project", {}).get("dependencies", [])
        dev_deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
        
        # Normalize names for comparison
        def normalize(name):
            return name.replace("_", "-").lower().split("=")[0].split(">")[0].strip()

        main_deps_norm = [normalize(d) for d in main_deps]
        dev_deps_norm = [normalize(d) for d in dev_deps]
        
        # These should BE in dev, NOT in main
        optional_pkgs = ["boto3", "firebase-admin", "google-cloud-aiplatform", "websockets"]
        
        for pkg in optional_pkgs:
            pkg_norm = normalize(pkg)
            self.assertNotIn(pkg_norm, main_deps_norm, f"{pkg} should not be in main dependencies")
            self.assertIn(pkg_norm, dev_deps_norm, f"{pkg} should be in dev dependencies")

if __name__ == "__main__":
    unittest.main()
