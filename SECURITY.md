# Security

Report a vulnerability privately to the repository owner (GitHub: @dhanushboopthy), not in a
public issue.

## Practices in this codebase

- Passwords hashed with Argon2; lockout after 5 wrong attempts for 15 minutes.
- Short-lived access tokens kept in memory; refresh tokens in httpOnly, SameSite=Strict
  cookies, stored hashed, rotated on use; reuse of an old token ends all sessions.
- Role checks in the API; owner-only fields never sent to other roles.
- Every change to business records is audit-logged with user, time, request id and diff.
- Production refuses to start with the development JWT secret or without secure cookies.
- Secrets only in `.env` (git-ignored). Serve over HTTPS. Nightly backups copied off-site.
- Dependabot keeps dependencies current; CI runs Bandit-style checks through ruff (`S` rules).
