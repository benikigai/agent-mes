Subject: Update on the auth service incident

Hi team,

Quick status on the auth-service rate-limit incident from last night:

ROOT CAUSE: rate limiter bucket on /v2/oauth was set to 100rpm, which
caused token-refresh storms during peak hours and surfaced as 429 errors
for customers using the new mobile client.

CURRENT STATE: change is in review with the platform team. The fix raises
the bucket to 500rpm to match the /v1/login parity we shipped last month.

ETA: deploy by EOD today. I'll send a follow-up confirming green metrics.

Let me know if you have questions.

— marcus
