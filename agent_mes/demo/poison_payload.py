"""Fake malicious dependency used in the Test stage demo.

When imported (which the StubBlaxelVerifier simulates on iter 1 → 2),
this module attempts an outbound HTTP call. The Blaxel sandbox stub
detects the egress and kills the microVM. This is the Stage 4 demo
gold moment — the egress kill at <25ms.

In real life this would be a transitive dep that someone added without
reviewing. AgentMES catches it because the blast_radius forbids egress
and the sandbox enforces it at the network layer.

DO NOT actually import this module from anywhere except the stub. The
stub fakes the import behavior — actually importing this would only
print a warning since the underlying http call is wrapped in try/except.
"""

POISON_DESTINATION = "evil.example.com"
POISON_REASON = "BLAST_RADIUS_VIOLATION: outbound network call to evil.example.com (allowed: false)"


def attempt_phone_home() -> dict[str, str]:
    """Simulate the malicious behavior. Returns a structured violation report
    that the stub Blaxel verifier turns into the kill log."""
    return {
        "destination": POISON_DESTINATION,
        "reason": POISON_REASON,
        "method": "HTTP GET",
        "blocked_by": "blaxel_egress_monitor",
    }
