# Release protocol

When the user requests a new Claude Session Linker release, treat the release as incomplete until every applicable step below succeeds:

1. Fetch `origin` and reconcile the working branch with the remote default branch without discarding local work.
2. Keep the release number centralized in `.app/VERSION`; update README/GUIA references when applicable and verify that no stale version remains.
3. Run the complete Python test suite, `py_compile`, and `git diff --check` before publishing.
4. Review the intended diff, stage only release files, commit, and push the default branch to `brunoflma/claude-session-linker` when the user explicitly authorized publication.
5. Synchronize `D:\OneDrive\Github\claude-session-linker` with the pushed commit using a fast-forward update and verify that both local repositories and `origin` resolve to the same commit.
6. Create and push the `v<version>` tag only after the branch push and validation succeed.
7. Build `claude-session-linker-<version>.zip` from the tagged tracked files, excluding repository metadata and local/runtime artifacts.
8. Create the GitHub release for the tag, upload that ZIP, and verify the published tag, asset name, asset digest, and download URL.
9. Report the commit, tag, synchronized repository paths, ZIP path, release URL, and validation evidence. Do not claim the release is complete if any one of these checks is missing.

Never publish secrets, account labels, session registries, backups, logs, virtual environments, caches, or conversation data.
