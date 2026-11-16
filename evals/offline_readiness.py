"""Read-only evidence readiness. No model, network, repair or grading execution."""
from collections import Counter
from pathlib import Path
from .quality import catalog, read_json, quality_report
from app.observability_report import aggregate_file


def exposure_report(root):
    dataset, _ = catalog(root)
    registry = read_json(Path(root)/'evals/exposure_registry.json')
    if set(registry) != {'schema_version','purpose','cases'} or registry['schema_version'] != 1:
        raise ValueError('Invalid exposure registry')
    expected = {c['id']:c['split'] for c in dataset['cases']}
    seen = set(); rows = []
    for row in registry['cases']:
        if set(row) != {'case_id','declared_split','exposure_status','basis'}:
            raise ValueError('Invalid exposure entry')
        cid = row['case_id']
        if cid in seen or expected.get(cid) != row['declared_split']:
            raise ValueError('Exposure/catalog mismatch')
        if row['exposure_status'] not in ('known_original','known_regression','not_verified_unseen'):
            raise ValueError('No unseen certification supported')
        if not isinstance(row['basis'],str) or not 1 <= len(row['basis']) <= 500:
            raise ValueError('Missing exposure basis')
        if row['declared_split'] in ('original','regression') and row['exposure_status'] != 'known_'+row['declared_split']:
            raise ValueError('Known cases cannot be relabeled')
        seen.add(cid);rows.append(row)
    if seen != set(expected):raise ValueError('Missing exposure cases')
    return {'catalog_cases':len(expected),'exposure_counts':dict(Counter(r['exposure_status'] for r in rows)),
            'verified_unseen_cases':0,'cases':rows,
            'limitation':'Declared holdout is a historical dataset label, not proof of unseen cases. Exposure is never erased by a new code revision.'}


def stability_report(records):
    # Reuse validated packet/verdict handling and strict version/replicate identity.
    report = quality_report(records, planned_cases=40, planned_replicates=3)
    report['scope'] = 'existing_artifacts_only_no_execution'
    report['three_replicates_required'] = True
    report['semantic_stability_certified'] = False
    report['limitation'] = 'Three same-version assessed replicas measure agreement, not correctness. Missing replicas remain missing; real and controlled results stay separate.'
    return report


def deviation_report(path):
    observed = aggregate_file(path)
    findings = []
    def add(code, action):findings.append({'code':code,'action':action})
    quality = observed['input_quality']
    if not quality['accepted_records']:add('NO_USABLE_EVENTS','Verify capture source before drawing conclusions; do not rerun paid calls automatically.')
    if quality['incomplete']:add('INCOMPLETE_CAPTURE','Preserve original log; inspect invalid/truncated/orphan counts. Never infer successful missing events.')
    provider = observed['provider_http_errors']['statuses']
    if provider.get('429'):add('PROVIDER_429','Pause new paid work; inspect bounded provider error and current quota. Do not bypass limits or retry automatically.')
    if any(int(k)>=500 and v for k,v in provider.items()):add('PROVIDER_5XX','Preserve failed attempt and uncertain reservation; inspect provider availability before any separately authorized retry.')
    if any(v and k not in ('200','201','204') for k,v in observed['http']['statuses'].items()):
        add('CLIENT_HTTP_NON_SUCCESS','Inspect route/authentication/input failure locally; provider status is not client HTTP status.')
    if any(v.get('unconfirmed_reconciliation_records',0) or v.get('unknown_reservation_records',0) for v in observed['costs']['by_mode'].values()):
        add('BUDGET_UNCERTAIN','Consult authoritative ledger read-only; retain uncertain reserve and stop before exceeding approved ceiling. Do not mark it paid.')
    if any(v for k,v in observed['functional_outcomes'].items() if k!='ok'):
        add('FUNCTIONAL_REVIEW','Inspect component outcome and visible answer; clarification or honest limitation is not automatically an incorrect answer.')
    return {'mode':'read_only_dry_run','actions_executed':False,'findings':findings,'observed':observed,
            'all_clear_claimed':False,'limitation':'No alert subscription, retry or remediation runs. Empty findings do not prove system health or semantic quality.'}
