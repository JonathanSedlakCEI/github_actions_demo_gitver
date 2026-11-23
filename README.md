# GitVersion NuGet demo 

This repository contains a small .NET 10 library and publishes it to GitHub
Packages when a pull request is merged into `main`. The package major version is
derived from the target framework major version; GitVersion uses Mainline mode
to advance the build component for ordinary merged changes and reset it to `0`
when the minor version advances.

## Version changes

Mark a breaking change in its commit message or pull request title/body with
`+semver: breaking`. The marker is included in the merge history so GitVersion
can advance the minor component. Minor bumps are reserved for this marker;
GitVersion major markers are disabled because the package major is reserved for
the .NET target framework major.

To select a prerelease, create a Git tag named `prerelease` on the latest commit
in the pull request before merging. Only that exact commit is checked. For
example (the single tag name must be moved when selecting a different commit):

```sh
git tag --force prerelease <latest-pr-commit>
git push --force origin refs/tags/prerelease
```

The workflow publishes prerelease builds as `major.minor.build-prerelease-01`.
If GitHub Packages already contains a version tagged with that pull request
number, the workflow advances its prerelease counter; a prior stable package
from that PR starts a new prerelease by advancing the build component. The
package's NuGet tags retain the PR number for this lookup.

The package major is read from the project `TargetFramework` when GitVersion
runs, so changing `net10.0` to `net11.0` makes the package major `11`. The
GitVersion configuration's `next-version` is also set to `10.0.0` as the local
baseline; the workflow overrides that baseline from the project target.
