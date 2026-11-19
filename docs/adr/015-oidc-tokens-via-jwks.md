# ADR 015: Tokens from an OIDC issuer, checked against its JWKS

**Context.** The v3 evaluation listed the local token signer as a gap: "in production, OIDC". With a shared HS256 secret, anyone who can verify a token can also mint one, and rotating the secret logs everyone out.

**Decision.**
- **When `OIDC_ISSUER` is set, the API accepts only tokens signed by that issuer.** It reads the issuer's discovery document, caches the published keys (JWKS) and checks the signature, issuer, audience (`OIDC_AUDIENCE`), expiry and `jti`.
- **Algorithms:** only RS256 and ES256, and the token's algorithm must match the key it names. That refuses `alg: none` and the classic confusion attack, HS256 signed with the public key.
- **Key rotation:**
  - the key set is re-read every 5 minutes;
  - a token with an unknown key id triggers a refresh, at most once every 30 s, so made-up key ids cannot flood the issuer;
  - if the issuer is down, the cached keys keep working, and with no keys at all the API answers 503, never "allow".
- **Scopes:** taken from `scope` (or `scp`), and only the API's own scopes are kept. Authorization still happens in code, as before.
- **Development provider:** `docker compose up` starts `navikt/mock-oauth2-server` (MIT, about 150 MB). `make token` gets a client-credentials token from it.
- **No local tokens in compose:** `JWT_SECRET` is cleared there, and the local signer refuses to issue tokens while OIDC is on. HS256 stays only for the offline tests and a quick run without compose.
- **Revocation:** by `jti` in the shared state database (ADR 014), for tokens from either source.
- **Readiness:** `/ready` reports whether the issuer's keys could be loaded.

**Measured** (`tests/unit/test_oidc.py`, 12 tests):
- Rejected: wrong issuer, wrong audience, expired token, missing `jti`, `alg: none`, HS256 signed with the public key, a token signed by another key under a known key id, and an ES256 token naming an RSA key.
- Accepted: the rotated key, after one refresh; the old key is rejected after it leaves the key set.
- Twenty tokens with an unknown key id caused no extra fetch.
- Provider down: 503 before any key is loaded, and cached keys after that.
- The API accepts the provider's tokens and refuses local ones.
- One real bug found while testing: an ES256 token naming an RSA key raised an exception (HTTP 500) instead of returning 401. The algorithm-must-match-key check fixed it.

**Alternatives.**
- Keycloak as the development provider: closer to a real deployment, but about 500 MB and slow to start, for the same API code.
- A provider written by us: less to download, but it would not show that the API works with a standard implementation.
- Token introspection on every request: always fresh revocation, but one network call per request and a hard dependency on the issuer.

**Consequences.**
- Moving to production means pointing `OIDC_ISSUER` and `OIDC_AUDIENCE` at the company's identity provider. Login, MFA and user lifecycle stay with it.
- The development provider grants any scope to any client; it must stay on the internal compose network.
