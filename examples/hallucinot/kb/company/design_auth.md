# Design doc: Authentication for the Quokka dashboard (fictional demo data)

Author: Lena Park. Status: Approved, June 2, 2026.

## Decision
We use server-side session cookies, not JWTs, for the dashboard. Sessions expire after 12 hours of inactivity. Single sign-on (SSO) via SAML is available only on the Enterprise plan.

## Why not JWT
JWTs cannot be revoked instantly without a deny list, and our security review required instant logout when an admin removes a user. Session cookies give us that with one database delete.

## Multi-factor authentication
MFA is optional for all plans and mandatory for admin accounts since July 2026. We support authenticator apps only; SMS codes were rejected because of SIM-swap risk.

## API keys
API access uses per-workspace API keys, rotated every 90 days. Keys are shown once at creation and stored hashed.
