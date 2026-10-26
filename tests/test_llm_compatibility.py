"""Exercise the real retained OpenAI client against a local protocol fixture."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


def test_upstream_openai_client_round_trip_and_holdout_absent(monkeypatch):
    from quantaalpha.llm.config import LLM_SETTINGS
    from quantaalpha.research.experiment import _llm_candidate
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == '/v1/chat/completions'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(payload)
            answer = {'name': 'local-contract-test', 'family': 'momentum', 'topk': 3, 'n_drop': 1, 'num_leaves': 8, 'max_depth': 3, 'reasoning': 'A bounded proposal based on validation feedback'}
            completion = {'id': 'offline-compatibility-test', 'object': 'chat.completion', 'created': 0, 'model': 'contract-model', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(answer)}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}
            data = json.dumps(completion).encode()
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
    monkeypatch.setenv('AQR_LLM_API_KEY', 'offline-contract-test-only')
    monkeypatch.setenv('AQR_LLM_PROTOCOL', 'openai')
    monkeypatch.setenv('AQR_LLM_BASE_URL', f'http://127.0.0.1:{server.server_port}/v1')
    monkeypatch.setenv('AQR_LLM_MODEL', 'contract-model')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    monkeypatch.delenv('CHAT_MODEL', raising=False)
    monkeypatch.delenv('REASONING_MODEL', raising=False)
    for name in ('openai_api_key', 'openai_base_url', 'chat_model'):
        monkeypatch.setattr(LLM_SETTINGS, name, getattr(LLM_SETTINGS, name))
    monkeypatch.setattr(LLM_SETTINGS, 'chat_stream', False)
    monkeypatch.setattr(LLM_SETTINGS, 'max_retry', 1)
    monkeypatch.setattr(LLM_SETTINGS, 'log_llm_chat_content', False)
    try:
        candidate, reason = _llm_candidate(0, 'test objective', [], [], {'validation': ['2021-01-01', '2021-12-31'], 'holdout': ['2030-01-01', '2031-12-31']})
        assert candidate['topk'] == 3
        assert reason.startswith('A bounded proposal')
        assert len(received) == 1
        assert received[0]['model'] == 'contract-model'
        serialized = json.dumps(received)
        assert '2030-01-01' not in serialized
        assert '2031-12-31' not in serialized
        assert 'offline-contract-test-only' not in serialized
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
