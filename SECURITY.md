# Security policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | Yes       |
| < 1.0   | No        |

Security fixes are released as patch versions of the latest minor release.

## Reporting a vulnerability

Please do not report security problems in a public issue, pull request or
discussion. Report them privately through GitHub: open this repository's
**Security** tab and choose **Report a vulnerability**
(<https://github.com/AKIVA-AI/toolkit-mmqa/security/advisories/new>). Include:

- what the problem is and its impact;
- steps or input files to reproduce it;
- the affected version or commit.

We aim to acknowledge a report within 7 days and ask for up to 90 days to
release a fix before public disclosure. We credit reporters who want to be
credited.

## Scope

**In scope:**

- File scanning and hashing logic (path traversal, symlink escape)
- Ed25519 signing and verification (key handling, signature bypass)
- CLI argument injection
- Dependency vulnerabilities in core and optional packages

**Out of scope:**

- Denial of service via large datasets (use `--max-file-size` to mitigate)
- Issues in development-only dependencies

## Security Considerations

This tool scans local files and writes reports. Treat scan reports as potentially sensitive -- they contain file paths and hashes from the scanned directory tree. When using `--sign`, protect your Ed25519 private key file with appropriate filesystem permissions.
