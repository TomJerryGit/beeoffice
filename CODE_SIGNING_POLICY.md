# Code Signing Policy

**Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).**

Project: BeeOffice  
License: MIT  
Repository: https://github.com/TomJerryGit/beeoffice

## Team roles

BeeOffice is currently maintained by a single maintainer:

- Authors/Committers: repository owner (`TomJerryGit`)
- Reviewers: repository owner; external PRs must be reviewed before merge
- Approvers: repository owner; each signing request must be manually approved

All team members must use MFA for GitHub and SignPath access.

## Privacy

See [PRIVACY.md](PRIVACY.md). The application does not transfer user documents
to networked services unless the user explicitly enables/configures an online
service (e.g. AI provider, cloud sync, update check).

## Policy

BeeOffice Windows release binaries are intended to be built from this public
repository and signed by a trusted code signing service. The signing key is
held by the signing service or project maintainer; it is never committed to
the repository.

## What is signed

- `BeeOffice.exe`
- Windows installer (`BeeOffice-Setup-*.exe`)
- Any shipped DLL or executable that is part of the release package

## Build provenance

- Source is built from a tagged commit on the public repository;
- Release builds are produced by the project's CI/build scripts;
- SHA-256 hashes are published with each release;
- Signing is performed only after tests and release checks pass.

## Verification

Users can verify a downloaded file with:

```powershell
Get-AuthenticodeSignature .\BeeOffice.exe | Format-List
Get-FileHash .\BeeOffice.exe -Algorithm SHA256
```

## Private key protection

- Private keys are stored in the signing service/HSM, never in git;
- CI accesses signing only through the service's short-lived credentials;
- Compromised credentials must be revoked and releases re-signed.

## Current status

- A local self-signed test certificate exists for pipeline testing only;
- Public releases are currently **unsigned** unless a trusted certificate
  or SignPath Foundation signing is approved;
- Unsigned builds must be clearly marked as unsigned in release notes.
