import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parent.parent
    / ".github"
    / "scripts"
    / "resolve_package_version.py"
)
SPEC = importlib.util.spec_from_file_location("resolve_package_version", MODULE_PATH)
VERSIONING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERSIONING)


class VersionForBuildTests(unittest.TestCase):
    def test_release_uses_gitversion_mainline_version(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.2.3", None, False),
            "10.2.3",
        )

    def test_first_prerelease_uses_two_digit_counter(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.2.3", None, True),
            "10.2.3-prerelease-01",
        )

    def test_existing_prerelease_increments_its_counter(self):
        self.assertEqual(
            VERSIONING.version_for_build(
                "10.2.3",
                "10.2.3-prerelease-09",
                True,
            ),
            "10.2.3-prerelease-10",
        )

    def test_existing_stable_pr_version_increments_build(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.2.3", "10.2.3", True),
            "10.2.4-prerelease-01",
        )

    def test_minor_bump_resets_build_from_gitversion(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.3.0", "10.2.3", True),
            "10.3.0-prerelease-01",
        )


if __name__ == "__main__":
    unittest.main()
