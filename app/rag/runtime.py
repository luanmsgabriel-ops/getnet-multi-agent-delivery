"""Explicit local RAG configuration. Shared cache contains public artifacts only."""
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from threading import RLock
import os
from .core import Index, load_snapshot
from .fetch import SOURCES
from .applicability import CorpusScopes
from .documentary import DocumentaryKnowledge
from .semantic import SemanticRetriever, SemanticUnavailable, MODEL_REVISION, verify_model
from app.knowledge import KnowledgeRag

_CACHE = OrderedDict()
_LOCK = RLock()
_SCOPE_PATH = Path(__file__).with_name('corpus_scopes.json')


def _configuration(env):
    adapter = env.get('GETNET_RAG_ADAPTER', 'documentary')
    retrieval = env.get('GETNET_RAG_RETRIEVAL', 'lexical')
    if adapter not in ('documentary', 'legacy') or retrieval not in ('lexical', 'semantic'):
        raise ValueError('Invalid explicit RAG configuration')
    if adapter == 'legacy' and retrieval != 'lexical':
        raise ValueError('Legacy adapter only supports lexical retrieval')
    model = env.get('GETNET_LOCAL_EMBEDDING_DIR', '')
    if retrieval == 'semantic' and not model:
        raise SemanticUnavailable('Semantic mode requires a local pinned model')
    return adapter, retrieval, model


def _fingerprint(corpus):
    root = Path(corpus).resolve()
    if not root.is_dir(): raise ValueError('Public corpus directory missing')
    files = sorted(root.glob('*.json'))
    if not files or len(files) > 100: raise ValueError('Public corpus size invalid')
    digest = sha256()
    for path in files:
        if path.stat().st_size > 1_000_000: raise ValueError('Public snapshot too large')
        digest.update(path.name.encode()); digest.update(b'\0'); digest.update(path.read_bytes())
    scope_hash = sha256(_SCOPE_PATH.read_bytes()).hexdigest()
    return files, digest.hexdigest(), scope_hash


def configured_knowledge(corpus, env=None, synthesizer=None):
    """Build per-caller adapter around cached public index/model; never cache clients.

    Explicit semantic startup validates provisioned bytes even on cache hits. No
    network fallback, automatic download, query cache or private-state cache exists.
    """
    env = os.environ if env is None else env
    adapter, retrieval, model = _configuration(env)
    files, corpus_hash, scope_hash = _fingerprint(corpus)
    model_dir = str(verify_model(model)) if retrieval == 'semantic' else ''
    key = (corpus_hash, scope_hash, retrieval, model_dir, MODEL_REVISION if model_dir else '')
    with _LOCK:
        resources = _CACHE.get(key)
        if resources is None:
            index = Index([load_snapshot(path, SOURCES) for path in files], ranker='hybrid')
            scopes = CorpusScopes(index, path=_SCOPE_PATH)
            semantic = SemanticRetriever(index, model_dir, candidate_filter=scopes.compatible, facet_provider=scopes.retrieval_facets) if model_dir else None
            # Do not accept a corpus/metadata replacement during construction.
            if _fingerprint(corpus)[1:] != (corpus_hash, scope_hash):
                raise ValueError('Public corpus changed during initialization')
            resources = (index, scopes, semantic)
            _CACHE[key] = resources
            while len(_CACHE) > 2: _CACHE.popitem(last=False)
        else:
            _CACHE.move_to_end(key)
    index, scopes, semantic = resources
    if adapter == 'legacy':
        knowledge = KnowledgeRag(index, reviewed_presentations=False, synthesizer=synthesizer)
    else:
        knowledge = DocumentaryKnowledge(index, scopes=scopes, semantic=semantic, synthesizer=synthesizer)
    knowledge._rag_configuration = {'adapter': adapter, 'retrieval': retrieval,
        'model_revision': MODEL_REVISION if semantic is not None else None,
        'coverage': 'not_assessed'}
    return knowledge


def configuration_status(knowledge):
    """Allowlisted public status only: no paths, credentials, identities or clients."""
    status = getattr(knowledge, '_rag_configuration', None)
    if status is None: return {'adapter': 'unconfigured', 'retrieval': 'unconfigured'}
    return {key: status[key] for key in ('adapter', 'retrieval', 'model_revision', 'coverage')}
