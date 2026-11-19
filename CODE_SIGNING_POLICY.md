# Code Signing Policy

Project: BeeOffice  
License: MIT  
Repository: https://github.com/TomJerryGit/beeoffice

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
