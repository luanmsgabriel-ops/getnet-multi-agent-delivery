# ADR 004: Identity comes from the token, authorization lives in the data layer

**Context.** The challenge payload carries `user_id`. Trusting it lets anyone read another merchant's receivables.
**Decision.** A JWT carries `sub`, `tenant`, `scope` and `jti`. A body `user_id` that differs from `sub` returns 403. The repository filters every query by `sub` and checks a scope per data type. No tool accepts a merchant id, so the model cannot ask for someone else's data.
**Alternatives.** API keys per merchant (no scopes or expiry). Authorization in prompts (models can be talked out of rules; code cannot).
**Consequences.** Isolation holds even when the model is fooled; it is tested at the repository and tool level. Production would swap the local HS256 signer for an OIDC provider.
