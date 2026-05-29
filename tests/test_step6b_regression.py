
import os
import sys
import subprocess
import unittest
from pathlib import Path
import importlib

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

class TestStep6bRegression(unittest.TestCase):
    def test_dependency_categorization(self):
        """Verifies that unused/optional dependencies are in dev section of pyproject.toml."""
        pyproject_path = project_root / "pyproject.toml"
        with open(pyproject_path, "r") as f:
            content = f.read()
        
        # Check they are NOT in the main dependencies list
        # We look for the [project] dependencies section and ensure they aren't there
        # and they ARE in the [project.optional-dependencies] dev section.
        
        import tomllib
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        
        main_deps = data.get("project", {}).get("dependencies", [])
        dev_deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
        
        optional_pkgs = ["boto3", "firebase-admin", "google-cloud-aiplatform", "websockets"]
        
        for pkg in optional_pkgs:
            # Note: package names might have version pins or slightly different naming (firebase-admin vs firebase_admin)
            pkg_base = pkg.split("=")[0].split(">")[0].replace("_", "-").lower()
            
            in_main = any(pkg_base in d.replace("_", "-").lower() for d in main_deps)
            in_dev = any(pkg_base in d.replace("_", "-").lower() for d in dev_deps)
            
            self.assertFalse(in_main, f"{pkg} should not be in main dependencies")
            self.assertTrue(in_dev, f"{pkg} should be in dev dependencies")

    def test_fix_code_loop_imports(self):
        """Verifies that pdd.fix_code_loop correctly imports internal modules."""
        # This will fail if the relative imports are broken or if it tries to fallback to absolute imports that don't exist
        try:
            import pdd.fix_code_loop as fix_code_loop
            importlib.reload(fix_code_loop)
            self.assertTrue(hasattr(fix_code_loop, 'run_agentic_crash'))
            self.assertTrue(hasattr(fix_code_loop, 'get_language'))
            self.assertTrue(hasattr(fix_code_loop, 'default_verify_cmd_for'))
            self.assertTrue(hasattr(fix_code_loop, 'fix_code_module_errors'))
        except ImportError as e:
            self.fail(f"Failed to import pdd.fix_code_loop correctly: {e}")

    def test_sync_determine_operation_import(self):
        """Verifies that pdd.sync_determine_operation correctly imports internal modules."""
        try:
            import pdd.sync_determine_operation as sync_op
            importlib.reload(sync_op)
            self.assertTrue(hasattr(sync_op, 'get_meta_dir'))
            # Test that it can resolve meta dir without raising ImportError
            # (Requires at least a mock or a real project structure, but we just check if it runs)
            res = sync_op.get_meta_dir(project_root=str(project_root))
            self.assertEqual(res, Path(project_root) / '.pdd' / 'meta')
        except ImportError as e:
            self.fail(f"Failed to import pdd.sync_determine_operation correctly: {e}")

    def test_interface_alignment_extract_step_report(self):
        """Verifies that extract_step_report is exported in pdd package."""
        import pdd
        self.assertTrue(hasattr(pdd, 'extract_step_report'), "pdd should export extract_step_report")

    def test_no_syntax_warnings_in_step_completion_markers(self):
        """Verifies that tests/test_e2e_issue_737_step_completion_markers.py has no syntax warnings."""
        test_file = project_root / "tests" / "test_e2e_issue_737_step_completion_markers.py"
        # We run it with -Wall to catch warnings during compilation
        result = subprocess.run(
            [sys.executable, "-Wall", "-m", "py_compile", str(test_file)],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("SyntaxWarning", result.stderr)

    def test_frontend_app_integration(self):
        """Verifies that App.tsx has BugModal and ChangeModal integrated."""
        app_tsx_path = project_root / "pdd" / "frontend" / "App.tsx"
        with open(app_tsx_path, "r") as f:
            content = f.read()
        
        # Check imports
        self.assertIn("import BugModal from './components/BugModal';", content)
        self.assertIn("import ChangeModal from './components/ChangeModal';", content)
        
        # Check state hooks
        self.assertIn("const [showBugModal, setShowBugModal] = useState(false);", content)
        self.assertIn("const [showChangeModal, setShowChangeModal] = useState(false);", content)
        
        # Check modal usage in JSX
        self.assertIn("<BugModal", content)
        self.assertIn("<ChangeModal", content)
        
        # Check "Use AI Assistant" buttons
        self.assertIn("Use AI Assistant", content)
        self.assertIn("onClick={handleOpenBugModal}", content)
        self.assertIn("onClick={handleOpenChangeModal}", content)

if __name__ == "__main__":
    unittest.main()
