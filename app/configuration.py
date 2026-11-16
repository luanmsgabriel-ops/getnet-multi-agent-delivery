"""Shared canonical configuration checks. No network, state creation or secrets output."""
import os


def validate_declared(env=None, *, injected_supervisor=False):
    env = os.environ if env is None else env
    choices = {
        'GETNET_ORCHESTRATION': ('deterministic', 'supervisor'),
        'GETNET_CONTEXT_MODEL': ('0',),
        'GETNET_WEB_SEARCH': ('0', '1'),
        'GETNET_RAG_GENERATION': ('disabled', 'validated'),
        'GETNET_DEMO_TICKETS': ('0', '1'),
        'GETNET_ALLOW_MODEL_NETWORK': ('0', '1'),
    }
    for name, allowed in choices.items():
        if env.get(name, allowed[0]) not in allowed:
            raise ValueError(name + ': unsupported canonical configuration')
    from app.rag.runtime import _configuration
    _configuration(env)
    from app.public_search import configuration
    search = configuration(env)
    mode = env.get('GETNET_ORCHESTRATION', 'deterministic')
    generation = env.get('GETNET_RAG_GENERATION', 'disabled')
    if generation != 'disabled' and mode != 'supervisor' and not injected_supervisor:
        raise ValueError('RAG generation requires explicitly configured budgeted supervisor')
    if env.get('GETNET_DEMO_TICKETS', '0') == '1' and not env.get('GETNET_DEMO_TICKET_DB'):
        raise ValueError('GETNET_DEMO_TICKET_DB is required for local tickets')
    return {'orchestration': mode, 'generation': generation, 'search': search}
