# Releasing Konstera SDK packages

This repo publishes **seven packages across three registries**. Each package has its own release workflow triggered by a specific git tag pattern.

## Package → tag → registry map

| Package | Current | Tag pattern | Registry | License |
|---|---|---|---|---|
| `Konstera.Sdk` | 0.3.0 | `sdk-dotnet-v<X.Y.Z>` | [nuget.org](https://www.nuget.org/) | BUSL-1.1 |
| `Konstera.Sdk.Contexts` | 1.0.0 | `sdk-dotnet-contexts-v<X.Y.Z>` | [nuget.org](https://www.nuget.org/) | Apache-2.0 |
| `konstera-sdk` (Python) | 0.6.0 | `sdk-python-v<X.Y.Z>` | [pypi.org](https://pypi.org/) | BUSL-1.1 |
| `konstera-sdk-contexts` (Python) | 1.0.0 | `sdk-python-contexts-v<X.Y.Z>` | [pypi.org](https://pypi.org/) | Apache-2.0 |
| `konstera-sdk` (TS) | 0.4.0 | `sdk-ts-v<X.Y.Z>` | [npmjs.com](https://www.npmjs.com/) | BUSL-1.1 |
| `konstera-sdk-contexts` (TS) | 1.0.0 | `sdk-ts-contexts-v<X.Y.Z>` | [npmjs.com](https://www.npmjs.com/) | Apache-2.0 |
| `@konstera/devx-mcp` | 0.1.0 | `devx-mcp-v<X.Y.Z>` | [npmjs.com](https://www.npmjs.com/) | Apache-2.0 |

## Release process

For any package:

1. **Bump the version** in the metadata file:
   - `.NET`: `<Version>X.Y.Z</Version>` in `dotnet/src/<Package>/<Package>.csproj`
   - Python: `version = "X.Y.Z"` in `python/pyproject.toml` or `python/konstera-sdk-contexts/pyproject.toml`
   - TypeScript: `"version": "X.Y.Z"` in `typescript/packages/konstera-sdk-contexts/package.json`
2. **If it's a context pack**: regenerate constants to catch any drift:
   ```sh
   python scripts/generate_constants.py
   ```
   The CI drift gate (`sdk-check.yml`) catches this on PR, but running locally first avoids a round trip.
3. **Commit**, open a PR, review, merge to `main`:
   ```sh
   git commit -am "bump(<package>): vX.Y.Z — <one-line reason>"
   ```
4. **Tag from `main`** and push:
   ```sh
   git checkout main && git pull
   git tag <tag-name>
   git push origin <tag-name>
   ```
5. The matching release workflow fires, builds, verifies version alignment, publishes to the registry, and creates a GitHub Release with the artefact attached.

### Example — releasing `konstera-sdk` 0.5.1

```sh
# 1. Edit python/pyproject.toml: version = "0.5.1"
# 2. (Not a context pack — skip generator)
git commit -am "bump(python-sdk): v0.5.1 — fix retry policy on cold-start"
# 3. Open PR → review → merge
# 4. Tag + push
git checkout main && git pull
git tag sdk-python-v0.5.1
git push origin sdk-python-v0.5.1
# 5. CI publishes to https://pypi.org/project/konstera-sdk/0.5.1/
```

## One-time secret setup (repo admin)

These are **one-time** per registry. Secret names must match the workflow references exactly.

### NuGet — API key

1. Sign in to [nuget.org](https://www.nuget.org/) as a user with push rights on `Konstera.*`.
2. Create an API key at `/account/apikeys`:
   - Key name: `Konstera.Sdk + Contexts (GitHub Actions)`
   - Scope: Push
   - Package owner: (your Konstera owner account)
   - Glob pattern: `Konstera.*`
   - Expiration: 365 days (reminder in RELEASING.md to rotate)
3. In GitHub repo settings → Secrets → Actions, create:
   - Name: `NUGET_API_KEY`
   - Value: (the API key from step 2)

Rotation: NuGet keys expire. Rotate before expiry and update the secret.

### PyPI — OIDC trusted publisher (no long-lived token)

Preferred because there's no token to leak or rotate.

**For `konstera-sdk`:**

1. On [pypi.org](https://pypi.org/), navigate to the pending publishers page (or project settings if the package is already published).
2. Add a GitHub trusted publisher:
   - PyPI project name: `konstera-sdk`
   - Owner: `Konstera`
   - Repository name: `sdk`
   - Workflow filename: `release-python.yml`
   - Environment: `pypi-sdk`
3. First successful publish promotes the pending publisher to active.

**For `konstera-sdk-contexts`:** repeat with project name `konstera-sdk-contexts`.

The workflow uses a GitHub Environment named `pypi-sdk` (it must match the "Environment name" on PyPI exactly). Create it in GitHub repo settings → Environments → New environment → `pypi-sdk`, and under "Deployment branches and tags" allow only tags matching `sdk-python-*`, so no branch or PR workflow can publish. No reviewers or wait timers are needed (optional: add a required reviewer for publish-time gating).

### npm — granular access token

Modern npm supports OIDC trusted publishing, but it requires the package to exist first. For the initial publish and until that migration happens:

1. On [npmjs.com](https://www.npmjs.com/), create the `konstera` organization (needed for the `@konstera/devx-mcp` scope). `konstera-sdk` and `konstera-sdk-contexts` are unscoped.
2. Create a **granular access token** (classic automation tokens are retired):
   - Permissions: Read and write
   - Packages: all packages (they don't exist yet), or `konstera-sdk`, `konstera-sdk-contexts` and `@konstera/*` after the first publish
   - Organizations: `konstera`
   - "Bypass two-factor authentication" enabled (CI can't answer a 2FA prompt)
   - Shortest expiry that covers the release window
3. In GitHub repo settings → Secrets → Actions, create:
   - Name: `NPM_TOKEN`
   - Value: (the granular token)
4. After the first successful publish, migrate each package to OIDC trusted publishing (see [npm docs](https://docs.npmjs.com/trusted-publishers)) and delete the token.

### npm provenance — requires this repo to stay public

The npm workflows publish with `--provenance`, and npm only accepts that from a **public** source repository. `Konstera/sdk` was made public on 2026-10-26 for this reason. If it ever goes private again, every npm publish fails at the publish step until `--provenance` is removed from the three `npm publish` lines (`release-typescript.yml` ×2, `release-devx-mcp.yml`).

## Semver policy

Follows the policy in [`ROADMAP.md`](./ROADMAP.md) §1:

**Standard Context Pack packages (`*-contexts`):**
- Adding a canonical name (glossary / skill / entity): **MINOR** bump.
- Removing or renaming a canonical name: **MAJOR** bump.
- Metadata-only change (description / alias / display name): **PATCH** bump.
- All three contexts packages (NuGet / PyPI / npm) must share the same `MAJOR.MINOR` as the pack JSON (`schemas/standard-context-pack-v1.json`). Patch numbers may diverge if one language ships a packaging-only fix.

**Main SDK packages (`Konstera.Sdk`, `konstera-sdk`):**
- Standard semver. New public API: MINOR. Breaking: MAJOR. Internal fix: PATCH.

Pre-release suffixes (`-rc1`, `-alpha.1`) are **not supported** by the current workflows. If needed, extend the tag matcher + add a `--pre-release` flag.

## Troubleshooting

### Workflow fails with "version mismatch"
The git tag version doesn't match the version in the package metadata file. Either (a) bump the metadata and re-tag, or (b) delete the mismatched tag and push a correct one. The verify step is intentional — it prevents accidentally publishing a 0.5.1 tagged as `sdk-python-v0.5.0`.

### NuGet publish fails with 409 Conflict
Version already published. NuGet forbids overwriting a version. Bump to a new patch and re-tag. The workflow uses `--skip-duplicate` so a re-run with the SAME tag succeeds (no-op), but a new tag with the SAME version fails here.

### PyPI publish fails with "trusted publisher not configured"
The pending publisher wasn't set up for this package. See the PyPI one-time setup above. Pending publishers expire 24h after creation if not used — if more time has passed, recreate.

### PyPI publish fails with "environment pypi-sdk not found"
Create a GitHub Environment named `pypi-sdk` (restricted to `sdk-python-*` tags) in repo settings.

### npm publish fails with "You must be logged in to publish"
`NPM_TOKEN` secret is missing or expired. See the npm one-time setup above. Automation tokens expire; rotate before expiry.

### npm publish fails with "ENEEDPROV: provenance requires OIDC"
`id-token: write` permission is missing from the workflow's `permissions` block. The provided workflow has this set — if you forked and the fork lost permissions, re-add.

### Context pack drift gate fails
The generated constants file differs from what `python scripts/generate_constants.py` produces. Run it locally, commit the result, then re-tag:
```sh
python scripts/generate_constants.py
git add -A && git commit -m "regen: pack constants"
git tag -d <bad-tag>
git push origin :<bad-tag>  # delete remote tag
git push origin main
git tag <same-tag>
git push origin <same-tag>
```

### I pushed a bad tag
Tags are refs, not immutable artefacts. Delete locally + remotely:
```sh
git tag -d <bad-tag>
git push origin :<bad-tag>
```
Then push a correct tag. If the workflow already ran and published to NuGet or PyPI, the published version stays — those registries don't allow unpublishing. Push a patch bump instead.

## Future hardening (post-v1.0)

- **Migrate npm to OIDC trusted publishing** once each npm package is published once with the token flow.- **Add provenance signing to NuGet packages** when NuGet.org gains OIDC support (as of 2026-10, not available).
- **Automated changelog** derived from Conventional Commits — currently relying on `generate_release_notes: true` which uses PR titles.
- **Cross-package version lockstep check** for context packs — a CI job that fails if the three contexts packages' versions don't match `schemas/standard-context-pack-v1.json`'s version.
- **Pre-release channel** (`-rc1`, `-alpha.1`) support with a separate workflow or tag matcher.
