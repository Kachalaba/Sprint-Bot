# Security Hardening Notes

## Secrets & Configuration Hygiene
- `.env.example` now emphasises secret storage outside of VCS and uses neutral
  placeholders instead of real passwords or tokens.
- Updated `.gitignore` to filter typical credential artefacts (`*.pem`,
  `*.p12`, `creds/`, etc.) to prevent accidental commits of private keys or
  service-account bundles.

## Personal Data Protection
- Added `utils.personal_data` with deterministic masking helpers used across
  loggers, Sentry, and notifications. Chat/user identifiers are hashed before
  leaving the process, preserving traceability without exposing raw IDs.
- JSON log formatter now sanitises sensitive fields automatically; tests were
  updated to assert masked outputs.
- Sentry initialisation applies a `before_send` scrubber that rewrites
  user/extra/context payloads to remove `chat_id`, `user_id`, and `username`.

## Runtime Resilience
- Telegram bot client explicitly uses aiohttp timeouts (`connect=5s`,
  `read=30s`) to avoid indefinite hangs on network failures.
- S3 backup client is created with botocore timeouts and bounded retry count
  to avoid runaway upload/download loops.
- Docker Compose defines a healthcheck for the bot container to signal failed
  processes to orchestrators promptly.

## Next Steps
- Consider rotating or externalising salts for masking if regulatory demands
  require stronger unlinkability between environments.
- Extend timeout configuration to Google Sheets access once gspread exposes a
  straightforward hook for HTTP client customisation.
