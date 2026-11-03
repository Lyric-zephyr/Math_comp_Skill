# Security policy

Security fixes are applied to the current development version. Older snapshots
do not have a separate maintenance commitment.

## Reporting a vulnerability

If this repository has private vulnerability reporting enabled, open its
**Security → Advisories → Report a vulnerability** page. Include the affected
version, impact, reproduction steps, and a minimal example without real secrets.

If private reporting is unavailable, open an issue asking the maintainer for a
private contact method. Do not include exploit details, credentials, or private
documents in that public issue. No response-time guarantee is currently offered.

## Credentials and data

- Use your own API credentials. Keys entered in the interface stay in memory
  and are passed to child adapters through their environment.
- Prompts and selected reference excerpts are sent to the chosen AI provider.
  Check that provider's data policies before using private material.
- GPT GUI sessions are stored outside the repository under
  `%LOCALAPPDATA%/MathCompSkill/browser/` on Windows. Treat that profile as account
  data and do not share it.
- Never attach unredacted keys, browser profiles, `.env` files, textbooks, or
  cached papers to reports. Revoke exposed credentials with the provider;
  deleting them from a later commit does not remove them from Git history.

One-click setup can install tools from package managers. Run the app from a
trusted checkout and review changes before running contributed code.
