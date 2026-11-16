"""Optional, local-only E5 retrieval. Ranking never establishes factual support.

Model files are provisioned separately, never downloaded by this module. Explicit
semantic configuration fails closed on missing dependencies, model or bad inputs.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import RLock

MODEL_ID = 'intfloat/multilingual-e5-small'
MODEL_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
MODEL_HASHES = {
    'onnx/model.onnx': 'ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665',
    'tokenizer.json': '0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39',
    'tokenizer_config.json': 'a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b',
    'special_tokens_map.json': 'd05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7',
    'config.json': '69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959',
    'README.md': '0038de97aee16258cecbad7ffda4b4febd6953e747a00e0ddbc8e6ed241e9c1c',
}
MAX_TOKENS = 512
RRF_K = 60
DENSE_POOL = 10
LEXICAL_POOL = 3


class SemanticUnavailable(RuntimeError):
    """Explicit semantic mode cannot operate; caller must not silently fall back."""


class SemanticInputError(ValueError):
    """Input cannot be embedded intact under the fixed budget."""


def verify_model(model_dir):
    """Verify owner-pinned bytes, without network, manifest trust or remote code."""
    if not isinstance(model_dir, (str, Path)) or not str(model_dir).strip():
        raise SemanticUnavailable('Local model directory required')
    root = Path(model_dir).resolve()
    if not root.is_dir():
        raise SemanticUnavailable('Local model directory missing')
    try:
        for name, expected in MODEL_HASHES.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise SemanticUnavailable('Required local model artifact missing')
            digest = sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise SemanticUnavailable('Local model artifact hash mismatch')
    except OSError as exc:
        raise SemanticUnavailable('Local model artifacts unreadable') from exc
    return root


class SemanticRetriever:
    """Fixed lexical/dense RRF returning intact, original indexed evidence.

    candidate_filter(question, candidate) is an eligibility predicate, not an
    entailment assertion. Both retrieval branches use it before fusion. No
    confidence threshold is inferred from cosine scores; coverage stays unassessed.
    """
    def __init__(self, index, model_dir, candidate_filter=None, facet_provider=None):
        root = verify_model(model_dir)
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise SemanticUnavailable('Install the separate semantic dependencies') from exc
        if candidate_filter is not None and not callable(candidate_filter):
            raise SemanticInputError('candidate_filter must be callable')
        self._np = np
        self._index = index
        self._entries = deepcopy(index.entries)
        self._known = {e['evidence_id']: i for i, e in enumerate(self._entries)}
        if facet_provider is not None and not callable(facet_provider):
            raise SemanticInputError('facet_provider must be callable')
        self._facet_provider = facet_provider
        self._filter = candidate_filter
        self._lock = RLock()
        try:
            # Disable native telemetry before constructing any inference session.
            ort.disable_telemetry_events()
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self._session = ort.InferenceSession(str(root / 'onnx/model.onnx'),
                sess_options=options, providers=['CPUExecutionProvider'])
            self._session.disable_fallback()
            self._inputs = tuple(item.name for item in self._session.get_inputs())
            if not set(self._inputs) <= {'input_ids', 'attention_mask', 'token_type_ids'}:
                raise SemanticUnavailable('Unexpected model input contract')
            self._tokenizer = Tokenizer.from_file(str(root / 'tokenizer.json'))
            self._tokenizer.no_truncation()
            self._tokenizer.enable_padding()
            passages = ['passage: ' + e['title'] + '\n' + e['text'] for e in self._entries]
            # Audit all passages before any inference; never partially index a corpus.
            self._tokenize(passages)
            batches = [self._encode(passages[i:i+4]) for i in range(0, len(passages), 4)]
            self._vectors = np.vstack(batches) if batches else np.empty((0, 384), dtype=np.float32)
            self._vectors.flags.writeable = False
        except (SemanticInputError, SemanticUnavailable):
            raise
        except Exception as exc:
            raise SemanticUnavailable('Local semantic initialization failed') from exc

    def _tokenize(self, texts):
        encoded = self._tokenizer.encode_batch(texts)
        if any(len(e.ids) > MAX_TOKENS or e.overflowing for e in encoded):
            raise SemanticInputError('Semantic input exceeds 512 tokens; not truncated')
        return encoded

    def _encode(self, texts):
        np = self._np
        with self._lock:
            encoded = self._tokenize(texts)
        data = {
            'input_ids': np.asarray([e.ids for e in encoded], dtype=np.int64),
            'attention_mask': np.asarray([e.attention_mask for e in encoded], dtype=np.int64),
            'token_type_ids': np.asarray([e.type_ids for e in encoded], dtype=np.int64),
        }
        try:
            output = self._session.run(None, {k: data[k] for k in self._inputs})[0]
            if output.ndim != 3 or output.shape != (*data['input_ids'].shape, 384):
                raise SemanticUnavailable('Unexpected model output contract')
            mask = data['attention_mask'][..., None]
            pooled = (output * mask).sum(axis=1) / mask.sum(axis=1)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            if not np.isfinite(pooled).all() or not (norms > 0).all():
                raise SemanticUnavailable('Invalid semantic vectors')
            return pooled / norms
        except SemanticUnavailable:
            raise
        except Exception as exc:
            raise SemanticUnavailable('Local semantic inference failed') from exc

    def search(self, question, market='BR', *, requested_services=()):
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise SemanticInputError('Question must contain 1-2000 characters')
        if market not in ('BR', 'GLOBAL'):
            raise SemanticInputError('Invalid market')
        from .applicability import validated_services
        try:
            demands = validated_services(question, requested_services)
        except ValueError as exc:
            raise SemanticInputError(str(exc)) from exc
        if demands and getattr(self, '_facet_provider', None) is None:
            raise SemanticInputError('Explicit demand allocation requires a reviewed facet provider')
        from .quality import product_scope_conflict
        # Even an empty corpus must not silently accept an over-budget question.
        vector = self._encode(['query: ' + question])[0]
        eligible = []
        for i, row in enumerate(self._entries):
            if row['market'] != market or product_scope_conflict(question, row):
                continue
            if self._filter is not None and not self._filter(question, deepcopy(row)):
                continue
            eligible.append(i)
        scores = self._vectors @ vector
        dense_order = sorted(eligible, key=lambda i: (-float(scores[i]), self._entries[i]['evidence_id']))
        # Demand diversity does not imply factual support. Keep the full query
        # embedding and original evidence; allocate at most three representatives
        # using reviewed scope labels, never body keyword guesses.
        provider = getattr(self, '_facet_provider', None)
        facets = {i: tuple(provider(question, deepcopy(self._entries[i]), demands)) if provider and len(demands)>1 else () for i in eligible}
        demanded = set(demands) if len(demands)>1 else set()
        representatives = []
        uncovered = set(demanded)
        if len(demanded) > 1:
            for i in dense_order:
                if uncovered.intersection(facets[i]):
                    representatives.append(i)
                    uncovered.difference_update(facets[i])
                if not uncovered or len(representatives) == 3:
                    break
        pool = set(representatives)
        for i in dense_order:
            if len(pool) >= DENSE_POOL: break
            pool.add(i)
        dense = [i for i in dense_order if i in pool]
        allowed = set(eligible)
        lexical = []
        for row in self._index.search(question, market=market)['candidates']:
            i = self._known.get(row.get('evidence_id'))
            if i in allowed and i not in lexical:
                lexical.append(i)
        lexical = lexical[:LEXICAL_POOL]
        fusion = {}
        ranks = {}
        for branch, order in (('lexical', lexical), ('dense', dense)):
            for rank, i in enumerate(order, 1):
                fusion[i] = fusion.get(i, 0.0) + 1.0 / (RRF_K + rank)
                ranks.setdefault(i, {})[branch] = rank
        order = sorted(fusion, key=lambda i: (-fusion[i], self._entries[i]['evidence_id']))
        chosen = set(representatives)
        for i in order:
            if len(chosen) >= 3: break
            chosen.add(i)
        selected = [i for i in order if i in chosen]
        candidates = []
        for i in selected:
            row = deepcopy(self._entries[i])
            row['retrieval'] = {'ranker': 'local_e5_rrf', 'score': fusion[i],
                'dense_score': float(scores[i]), 'branch_ranks': ranks[i],
                'rrf_k': RRF_K, 'model_id': MODEL_ID, 'model_revision': MODEL_REVISION,
                'coverage': 'not_assessed', 'demand_facets': list(facets[i]),
                'diversified': bool(representatives), 'facets_unallocated': sorted(uncovered)}
            candidates.append(row)
        return {'status': 'candidates' if candidates else 'insufficient_evidence',
                'coverage': 'not_assessed', 'candidates': candidates}
