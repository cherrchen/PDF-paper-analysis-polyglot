# GitHub settings

[中文](./github-settings.md) | [English](./github-settings.en.md)

These `main` rules are required. This document does not claim they were applied by bootstrap.

- Require pull requests
- Require status check `CI / gate`
- Require conversation resolution
- Block force pushes
- Block branch deletion
- Require linear history (squash merge)

Direct pushes to `main` are forbidden. Approval count may be zero for a single maintainer.

Apply these in GitHub Settings → Rulesets (or classic branch protection) after the remote exists.
