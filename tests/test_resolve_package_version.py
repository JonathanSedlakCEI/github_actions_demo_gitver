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
    def test_first_stable_release_uses_gitversion_baseline(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.2.3", None, False),
            "10.2.3",
        )

    def test_plain_merged_change_increments_latest_stable_patch(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.0.0", None, False, "10.0.0"),
            "10.0.1",
        )

    def test_breaking_change_increments_minor_and_resets_patch(self):
        self.assertEqual(
            VERSIONING.version_for_build(
                "10.0.0",
                None,
                False,
                "10.0.5",
                is_breaking_change=True,
            ),
            "10.1.0",
        )

    def test_gitversion_increment_is_not_applied_twice(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.0.1", None, False, "10.0.0"),
            "10.0.1",
        )

    def test_stable_rerun_reuses_this_pull_requests_version(self):
        self.assertEqual(
            VERSIONING.version_for_build("10.0.0", "10.0.1", False, "10.0.1"),
            "10.0.1",
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

    def test_latest_stable_ignores_prerelease_versions(self):
        self.assertEqual(
            VERSIONING.latest_stable_version(
                [
                    {"name": "10.0.1-prerelease-12"},
                    {"name": "10.0.0"},
                    {"name": "10.0.2"},
                ]
            ),
            "10.0.2",
        )


class AuthorizationSafeRedirectHandlerTests(unittest.TestCase):
    def setUp(self):
        self.handler = VERSIONING.AuthorizationSafeRedirectHandler()
        self.request = VERSIONING.urllib.request.Request(
            "https://nuget.pkg.github.com/owner/package.nupkg",
            headers={
                "Authorization": "Basic secret",
                "Accept": "application/octet-stream",
            },
        )

    def test_cross_origin_redirect_drops_authorization(self):
        redirected = self.handler.redirect_request(
            self.request,
            None,
            302,
            "Found",
            {},
            "https://packagesstorage.blob.core.windows.net/package.nupkg?sig=redacted",
        )

        self.assertNotIn("Authorization", redirected.headers)
        self.assertEqual(redirected.headers["Accept"], "application/octet-stream")

    def test_same_origin_redirect_keeps_authorization(self):
        redirected = self.handler.redirect_request(
            self.request,
            None,
            302,
            "Found",
            {},
            "https://nuget.pkg.github.com/owner/other.nupkg",
        )

        self.assertEqual(redirected.headers["Authorization"], "Basic secret")


if __name__ == "__main__":
    unittest.main()
