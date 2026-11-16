"""Small offline judge CI: no credentials, model calls or broad application suite."""
import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
MODULES = ['test_memory_literal_anchors', 'test_eval_judging', 'test_remote_judge',
           'test_focal_evaluation.FocalEvaluation', 'test_judge_ci', 'test_structured_judge_wire', 'test_provider_error_reporting', 'test_execution_observations', 'test_judge_single_evidence', 'test_offline_readiness', 'test_memory_final_points', 'test_judge_missing_evidence']

def main():
    os.environ['GETNET_ALLOW_MODEL_NETWORK'] = '0'
    # Defense in depth beyond CI's --network none; MockTransport still works.
    with tempfile.TemporaryDirectory(prefix='getnet-offline-ci-') as state, \
         patch.dict(os.environ, {'GETNET_AUTH_MODE':'demo', 'GETNET_CONTEXT_DB':str(Path(state)/'context.db')}), \
         patch('socket.socket.connect', side_effect=AssertionError('Offline CI: network prohibited')), \
         patch('socket.socket.connect_ex', side_effect=AssertionError('Offline CI: network prohibited')):
        suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    print('Focused judge contracts only; controlled outputs do not prove semantic stability.')
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__': raise SystemExit(main())
