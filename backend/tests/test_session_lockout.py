def test_require_auth_rejects_missing_cookie():
    from app import create_app
    app = create_app('development')
    client = app.test_client()

    r = client.get('/api/auth/me')
    assert r.status_code == 401
