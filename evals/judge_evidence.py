"""One canonical evidence representation; no expected answers or score repair."""
MAX_CLAIM_CHECKS = 192

def checks_from_audit(audit, amap, rmap):
    if set(audit) != set(amap):
        raise ValueError('incomplete segment audit')
    checks = []
    for aid, item in audit.items():
        ids = item['evidence_segments']
        if len(ids) != len(set(ids)) or any(rid not in rmap for rid in ids):
            raise ValueError('invalid audit source')
        if item['kind'] != 'product_claim':
            continue
        assessment = item['assessment']
        if assessment == 'not_factual':
            raise ValueError('product claim cannot be nonfactual')
        if assessment in ('supported', 'contradicted', 'ambiguous') and not ids:
            raise ValueError('factual decision requires evidence')
        if not ids:
            if assessment != 'insufficient':
                raise ValueError('factual decision requires evidence')
            checks.append(dict(answer_quote=aid, reference_quote=None,
                evidence_id=None, assessment='insufficient'))
            if len(checks) > MAX_CLAIM_CHECKS:
                raise ValueError('bounded claim capacity exceeded')
        for rid in ids:
            owner, _ = rmap[rid]
            checks.append(dict(answer_quote=aid, reference_quote=rid,
                evidence_id=owner, assessment='insufficient' if assessment == 'ambiguous' else assessment))
            if len(checks) > MAX_CLAIM_CHECKS:
                raise ValueError('bounded claim capacity exceeded')
    return checks

def evaluator_identity(generator_model, judge_model):
    """Report known identity, not semantic independence or human review."""
    def provider(model):
        return model.split('/', 1)[0] if isinstance(model, str) and '/' in model else None
    return {'generator_model': generator_model, 'judge_model': judge_model,
            'same_model': generator_model == judge_model if generator_model and judge_model else None,
            'same_provider': provider(generator_model) == provider(judge_model) if provider(generator_model) and provider(judge_model) else None,
            'model_family_independence': 'not_demonstrated',
            'human_review': 'not_demonstrated'}
