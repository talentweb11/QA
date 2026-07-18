from app import create_app


def test_health():
    client = create_app('development').test_client()
    resp = client.get('/api/health')
    assert resp.status_code == 200
    assert resp.get_json() == {'status': 'ok'}
