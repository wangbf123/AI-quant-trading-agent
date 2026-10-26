from fastapi.testclient import TestClient


def test_settings_redact_credentials_and_preserve_masked_binding(monkeypatch, tmp_path):
    import app
    path = tmp_path / '.env'
    path.write_text('OPENAI_API_KEY=offline-private-test-only\nAQR_DATABASE_URL=postgresql://user:offline-password@db/test\n')
    monkeypatch.setattr(app, 'DOTENV_PATH', path)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    with TestClient(app.app) as client:
        response = client.get('/api/v1/system/config')
        assert response.status_code == 200
        assert 'offline-private-test-only' not in response.text
        assert 'offline-password' not in response.text
        assert response.json()['data']['env']['OPENAI_API_KEY'] == '********'
        saved = client.put('/api/v1/system/config', json={'OPENAI_API_KEY': '********', 'OPENAI_BASE_URL': 'http://127.0.0.1:9000/v1'})
        assert saved.status_code == 200
        assert 'OPENAI_API_KEY=offline-private-test-only' in path.read_text()
        assert client.put('/api/v1/system/config', json={'CHAT_MODEL': 'model\nINJECTED=value'}).status_code == 422
