"""Duolink's own use cases (Milestone 16, ADR 0012): admin sign-in, companies, users across
companies, activity and plans. Only these services read across companies, on sessions that
`api/deps.get_platform_admin` put in platform mode."""
