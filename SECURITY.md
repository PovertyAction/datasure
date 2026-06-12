# Security Policy

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Instead, use one of these private channels:

1. **GitHub private vulnerability reporting** (preferred): use
   [Report a vulnerability](https://github.com/PovertyAction/datasure/security/advisories/new)
   under the repository's Security tab.
2. **Email**: <researchsupport@poverty-action.org> with the subject line
   `DataSure Security Report`.

In your report, please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce, ideally with a minimal example
- The DataSure version and operating system affected
- Any suggested remediation, if you have one

We will acknowledge your report within 5 business days, keep you informed of
progress, and credit you in the release notes when the fix ships (unless you
prefer to remain anonymous).

## Supported Versions

Security fixes are applied to the most recent release only.

| Version        | Supported |
| -------------- | --------- |
| Latest release | Yes       |
| Older releases | No        |

If you are running an older version, please upgrade to the latest release
before reporting an issue.

## Security Model

DataSure is a locally run, single-user desktop application. Understanding its
security model helps assess the impact of potential issues:

- **Local-only server**: the Streamlit server binds to `localhost` by default
  and is not reachable from the network unless explicitly launched with a
  different `--host`.
- **Credential storage**: SurveyCTO credentials are stored in the operating
  system keyring (Windows Credential Manager, macOS Keychain, or Secret
  Service on Linux), never in plaintext files. Only non-sensitive metadata
  (server name, username) is written to disk.
- **Data storage**: survey data is stored locally in DuckDB database files
  under the user's cache directory. DataSure does not transmit survey data to
  any service other than the SurveyCTO server the user configures.
- **Outbound connections**: the application makes outbound HTTPS requests
  only to SurveyCTO servers configured by the user. Telemetry is disabled.

Issues that require an attacker to already have control of the user's local
account are generally out of scope, since the application offers no protection
boundary beyond the operating system user. Vulnerabilities in credential
handling, in processing untrusted data files, or that expose data over the
network are firmly in scope.

## Data Protection Responsibilities

DataSure is built for survey data workflows that may involve personally
identifiable information (PII). The application keeps all data local, but
protecting the machine it runs on is the operator's responsibility. Follow
your organization's data protection policies regarding disk encryption,
device access, and handling of confidential data.
