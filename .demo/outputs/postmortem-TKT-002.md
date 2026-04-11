# Postmortem: incident-2026-04-09

**Service:** auth-service
**Date:** 2026-04-09
**Time:** 14:30 PDT (28 minute outage)
**Severity:** P1 — full login outage
**Author:** marcus

## Summary

At 14:30 PDT on 2026-04-09 the auth-service began returning 429 and 503
responses on the `/v1/login` endpoint, blocking all customer logins for
~28 minutes. Service was restored when the morning deploy was rolled back.

## Timeline

- 09:14 PDT — morning deploy ships rate-limiter config change
- 14:30 PDT — login traffic peaks, rate-limiter saturates
- 14:32 PDT — first customer report in #incidents
- 14:38 PDT — on-call paged, identifies the deploy as suspect
- 14:51 PDT — rollback triggered
- 14:58 PDT — service fully restored

## Root Cause

The morning deploy included a rate-limiter bucket size change that was
applied uniformly across all endpoints. The login endpoint's organic
traffic exceeds the new bucket size at peak hours.

## 5 Whys

Why did the service go down? Rate-limiter rejected legitimate login traffic.
Why did the rate-limiter reject it? Bucket size was set too low for peak load.
Why was the bucket size too low? Deploy applied a uniform value across endpoints.
Why was a uniform value used? Config change wasn't validated against per-endpoint load profiles.
Why wasn't there a validation gate? Action item AI-24 from inc_201 was never implemented.

## Action Items

| # | Item | Owner | Due |
| - | ---- | ----- | --- |
| AI-31 | Implement deploy-pipeline validation gate (resurrect AI-24) | sarah | 2026-04-18 |
| AI-32 | Per-endpoint rate-limiter config tests in CI | jamie | 2026-04-25 |
| AI-33 | Postmortem readout in eng all-hands | marcus | 2026-04-15 |
