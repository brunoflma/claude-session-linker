# Application delivery and release rule

This rule applies from 2026-09-21 onward. A requested delivery of application improvements must include the release process below when publication is authorized for the task. A push to `master` alone does not update the downloadable release. Do not describe an application update as released until its tag, packages, published release and public downloads have been verified.

Documentation, website, profile and illustration changes alone do not require a new application version. Ordinary questions are not authorization to publish a release. Honor an explicit request to keep a change unpublished.

## Before a version is published

1. Fetch `origin` and tags, inspect the working tree and reconcile with `origin/master` without discarding local work.
2. Keep the version centralized in `.app/VERSION`. Increase it for changed application code, installers, runtime assets or dependencies; document that version in `CHANGELOG.md`. Do not reuse an already released version for changed application files.
3. Run the complete application suite, release-tool tests, Python syntax checks, presentation checks and `git diff --check`. Resolve failures; do not remove meaningful tests merely to publish.
4. Commit the reviewed changes and push `master` within the task's publication authorization. Wait for `Validate application` to pass for every configured Windows/macOS runner. This workflow also validates extracted packages with synthetic profiles. Its checks do not authorize access to real conversations.
5. Synchronize `D:\OneDrive\Github\claude-session-linker` with a fast-forward update. If this canonical checkout is missing, create a clean clone at that path. Verify that the working checkout, canonical checkout and `origin/master` resolve to the same intended commit before tagging.
6. Create and push the annotated tag `v<version>` only for the validated commit. Never move or replace a published tag. Version tags are the trigger for `Publish release`; untagged commits do not silently replace downloads.

## Automated publication contract

- `Validate application` runs on application pushes/PRs and is reused by the release workflow. It checks version progression, tests and package smoke checks on Windows and macOS, including Intel and Apple Silicon.
- `scripts/release_bundle.py` builds from the tagged Git objects with a strict file allowlist. Never ZIP the current folder, copy an old release ZIP, or include the working tree's runtime files.
- Generate `claude-session-linker-<version>-windows.zip` and `claude-session-linker-<version>-macos.zip`, plus byte-identical `claude-session-linker-windows.zip` and `claude-session-linker-macos.zip` aliases. The aliases provide stable `/releases/latest/download/...` URLs; they are separate assets on each release, not replacements of older releases.
- Each package includes its exact tag, commit, version and platform in `RELEASE.json`. Publish `release-manifest.json` and `SHA256SUMS.txt` alongside the ZIPs. Preserve executable permissions and LF content in macOS launchers.
- Create a draft, attach all expected assets, verify their names, sizes and server-reported SHA-256 digests, then publish. Verify the public download bytes afterward. Never overwrite an existing published asset or silently replace a mismatched draft asset.
- Rerunning the workflow may fill in missing assets of a matching draft or verify an already published release. It must fail on a tag, version, commit or asset mismatch.
- Mark the new stable version as Latest only when it is newer than the already published stable releases. Keep earlier releases available for rollback.
- After the first automated release, maintain website and guide buttons on the stable release download links. Update installation instructions whenever launcher names or packaging change.

## Completion evidence

Report the release URL, version/tag, source commit, both synchronized checkout paths, local artifact location, Windows/macOS CI results and verified download links/digests. Clearly separate a pending draft, failed workflow or skipped platform check from a completed release.

Never publish secrets, account labels, session registries, backups, logs, virtual environments, caches or conversation data. Do not launch operations against real Claude profiles as part of release testing. Use synthetic temporary profiles and do not force-close a user's Claude Desktop.

See `RELEASING.md` for the operational commands and recovery procedure.
