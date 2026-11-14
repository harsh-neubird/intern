# Postmortem: Dashboard outage on October 21, 2026 (fictional demo data)

Author: Sam Ortiz (SRE). Severity: SEV-1. Duration: 47 minutes (14:05–14:52 Pacific).

## What happened
The dashboard and API returned errors for 47 minutes. The root cause was a database connection pool exhaustion after a config change raised the API worker count from 16 to 64 without raising the Postgres max_connections limit (still 200).

## Impact
About 30% of API requests failed during the window. October monthly uptime came in at 99.89%, just below the 99.9% SLA, so Acme Corp and two other enterprise customers are owed a 10% service credit for October.

## Fix
We rolled back the worker count to 16 at 14:49. Long term, we added PgBouncer in front of Postgres (shipped October 28) and an alert when pool usage exceeds 80%.

## Decisions
We decided NOT to move to a managed database this quarter; it is revisited in Q1 2027. Config changes to worker counts now require a second reviewer.
