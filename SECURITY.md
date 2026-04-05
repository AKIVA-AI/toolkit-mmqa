# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Email <security@akiva.com> with:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Affected version(s)

We will acknowledge receipt within 48 hours and provide a triage assessment within 7 business days.

## Disclosure Policy

We follow coordinated disclosure. We ask that you give us 90 days to address the issue before public disclosure.

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
