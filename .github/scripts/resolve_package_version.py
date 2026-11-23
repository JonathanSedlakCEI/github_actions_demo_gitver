#!/usr/bin/env python3
"""Resolve the NuGet version, using GitHub Packages as per-PR prerelease history."""

import argparse
import base64
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET


VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)(?:-prerelease-(?P<prerelease>\d+))?$"
)


class AuthorizationSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep package credentials on the origin that issued them."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        redirected = super().redirect_request(
            request, response, code, message, headers, new_url
        )
        if redirected is None:
            return None

        source = urllib.parse.urlsplit(request.full_url)
        destination = urllib.parse.urlsplit(new_url)
        source_origin = (source.scheme.lower(), source.hostname, source.port)
        destination_origin = (
            destination.scheme.lower(),
            destination.hostname,
            destination.port,
        )
        if source_origin != destination_origin:
            for request_headers in (redirected.headers, redirected.unredirected_hdrs):
                for name in tuple(request_headers):
                    if name.lower() == "authorization":
                        del request_headers[name]
        return redirected


def version_for_build(
    base_version,
    latest_for_pr,
    is_prerelease,
    latest_stable=None,
    is_breaking_change=False,
):
    """Resolve a published version from GitVersion and package history."""
    match = VERSION_PATTERN.fullmatch(base_version)
    if match is None:
        raise ValueError(f"GitVersion returned an unsupported version: {base_version}")
    major, minor, patch = (int(match[name]) for name in ("major", "minor", "patch"))

    if not is_prerelease:
        previous_pr_version = VERSION_PATTERN.fullmatch(latest_for_pr or "")
        if previous_pr_version and previous_pr_version["prerelease"] is None:
            return latest_for_pr

        latest = VERSION_PATTERN.fullmatch(latest_stable or "")
        if latest and int(latest["major"]) == major:
            latest_minor = int(latest["minor"])
            latest_patch = int(latest["patch"])
            if is_breaking_change:
                if minor <= latest_minor:
                    return f"{major}.{latest_minor + 1}.0"
            elif minor < latest_minor or (
                minor == latest_minor and patch <= latest_patch
            ):
                return f"{major}.{latest_minor}.{latest_patch + 1}"
        return f"{major}.{minor}.{patch}"

    latest = VERSION_PATTERN.fullmatch(latest_for_pr or "")
    if latest and latest["prerelease"] is not None:
        return (
            f"{latest['major']}.{latest['minor']}.{latest['patch']}-prerelease-"
            f"{int(latest['prerelease']) + 1:02d}"
        )
    if latest and latest["prerelease"] is None:
        if int(latest["major"]) == major and int(latest["minor"]) == minor:
            patch = max(patch, int(latest["patch"]) + 1)

    return f"{major}.{minor}.{patch}-prerelease-01"


def request_json(url, token):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response), response.headers.get("Link", "")


def list_package_versions(api_url, owner, owner_type, package_id, token):
    owner_path = "orgs" if owner_type.lower() == "organization" else "users"
    endpoint = (
        f"{api_url.rstrip('/')}/{owner_path}/{urllib.parse.quote(owner, safe='')}"
        f"/packages/nuget/{urllib.parse.quote(package_id, safe='')}/versions?per_page=100"
    )
    versions = []
    while endpoint:
        try:
            page, link_header = request_json(endpoint, token)
        except urllib.error.HTTPError as error:
            if error.code == 404 and not versions:
                return []
            raise
        versions.extend(page)
        next_link = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        endpoint = next_link.group(1) if next_link else ""
    return sorted(versions, key=lambda version: version["created_at"], reverse=True)


def package_base_address(owner, token):
    username = os.environ.get("GITHUB_ACTOR", owner)
    credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
    request = urllib.request.Request(
        f"https://nuget.pkg.github.com/{urllib.parse.quote(owner, safe='')}/index.json",
        headers={"Authorization": f"Basic {credentials}"},
    )
    with urllib.request.urlopen(request) as response:
        index = json.load(response)
    for resource in index["resources"]:
        if "PackageBaseAddress" in resource["@type"]:
            return resource["@id"].rstrip("/") + "/"
    raise RuntimeError("GitHub Packages NuGet feed has no PackageBaseAddress resource.")


def tags_for_package(base_address, package_id, version, owner, token):
    username = os.environ.get("GITHUB_ACTOR", owner)
    credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
    package = package_id.lower()
    normalized_version = version.lower()
    url = urllib.parse.urljoin(
        base_address,
        f"{package}/{normalized_version}/{package}.{normalized_version}.nupkg",
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {credentials}"})
    opener = urllib.request.build_opener(AuthorizationSafeRedirectHandler())
    with opener.open(request) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    nuspec = next(name for name in archive.namelist() if name.lower().endswith(".nuspec"))
    root = ET.fromstring(archive.read(nuspec))
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "tags":
            return set((element.text or "").split())
    return set()


def latest_version_for_pr(versions, package_id, owner, token, pr_number):
    if not versions:
        return None
    base_address = package_base_address(owner, token)
    pr_tag = f"pr-{pr_number}"
    for package_version in versions:
        version = package_version["name"]
        if pr_tag in tags_for_package(base_address, package_id, version, owner, token):
            return version
    return None


def latest_stable_version(versions):
    stable_versions = []
    for package_version in versions:
        name = package_version["name"]
        match = VERSION_PATTERN.fullmatch(name)
        if match and match["prerelease"] is None:
            stable_versions.append(
                (
                    int(match["major"]),
                    int(match["minor"]),
                    int(match["patch"]),
                    name,
                )
            )
    return max(stable_versions, default=(0, 0, 0, None))[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--owner-type", required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--base-version", required=True)
    parser.add_argument("--prerelease", choices=("true", "false"), required=True)
    parser.add_argument("--breaking-change", choices=("true", "false"), required=True)
    args = parser.parse_args()

    token = os.environ["GH_TOKEN"]
    versions = list_package_versions(
        os.environ["GITHUB_API_URL"],
        args.owner,
        args.owner_type,
        args.package_id,
        token,
    )
    latest = latest_version_for_pr(versions, args.package_id, args.owner, token, args.pr_number)
    print(
        version_for_build(
            args.base_version,
            latest,
            args.prerelease == "true",
            latest_stable_version(versions),
            args.breaking_change == "true",
        )
    )


if __name__ == "__main__":
    main()
