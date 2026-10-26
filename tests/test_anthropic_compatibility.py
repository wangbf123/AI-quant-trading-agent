import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest


@pytest.mark.parametrize('auth_mode', ['api_key', 'bearer'])
def test_step_plan_native_messages_protocol(monkeypatch, auth_mode):
    from quantaalpha.llm.config import LLM_SETTINGS
    from quantaalpha.research.experiment import _llm_candidate
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == '/step_plan/v1/messages'
            if auth_mode == 'api_key':
                assert self.headers.get('x-api-key') == 'offline-contract-test-only'
                assert self.headers.get('authorization') is None
            else:
                assert self.headers.get('authorization') == 'Bearer offline-contract-test-only'
                assert self.headers.get('x-api-key') is None
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(body)
            candidate = {'family': 'price_volume', 'topk': 5, 'n_drop': 1, 'num_leaves': 8, 'max_depth': 3, 'reasoning': 'A native Messages proposal'}
            answer = {'id': 'local-messages-test', 'type': 'message', 'role': 'assistant', 'model': 'step-5-preview', 'content': [{'type': 'text', 'text': json.dumps(candidate)}], 'stop_reason': 'end_turn', 'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 10}}
            data = json.dumps(answer).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('AQR_LLM_PROTOCOL', 'anthropic')
    monkeypatch.setenv('AQR_LLM_API_KEY', 'offline-contract-test-only')
    monkeypatch.setenv('AQR_LLM_BASE_URL', f'http://127.0.0.1:{server.server_port}/step_plan')
    monkeypatch.setenv('AQR_LLM_MODEL', 'step-5-preview')
    monkeypatch.setenv('AQR_LLM_AUTH_MODE', auth_mode)
    for key in ['OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CHAT_MODEL', 'REASONING_MODEL']:
        monkeypatch.delenv(key, raising=False)
    for key in ['openai_api_key', 'openai_base_url', 'chat_model']:
        monkeypatch.setattr(LLM_SETTINGS, key, getattr(LLM_SETTINGS, key))
    monkeypatch.setattr(LLM_SETTINGS, 'max_retry', 1)
    try:
        candidate, reason = _llm_candidate(0, 'native compatibility', [], [], {'validation': ['2021-01-01', '2021-12-31'], 'holdout': ['2030-01-01', '2030-12-31']})
        assert candidate['family'] == 'price_volume'
        assert reason == 'A native Messages proposal'
        assert len(received) == 1
        assert received[0]['model'] == 'step-5-preview'
        assert received[0]['system']
        assert 'response_format' not in received[0]
        serialized = json.dumps(received)
        assert '2030-01-01' not in serialized
        assert 'offline-contract-test-only' not in serialized
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
