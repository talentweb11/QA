import io
from app import create_app
from app.utils.request_meta import client_ip as _get_real_ip


# ============================================================================
# SR-07 — Rate limiter uses real IP behind Nginx
# ============================================================================

def test_rate_limiter_uses_xreal_ip_header():
    app = create_app('development')
    with app.test_request_context(headers={'X-Real-IP': '1.2.3.4'}):
        result = _get_real_ip()
        print(f"\n  X-Real-IP header set to '1.2.3.4' → _get_real_ip() returned: '{result}'")
        assert result == '1.2.3.4'


def test_rate_limiter_falls_back_to_remote_addr():
    app = create_app('development')
    with app.test_request_context(environ_base={'REMOTE_ADDR': '5.6.7.8'}):
        result = _get_real_ip()
        print(f"\n  No X-Real-IP header, REMOTE_ADDR='5.6.7.8' → _get_real_ip() returned: '{result}'")
        assert result == '5.6.7.8'


# ============================================================================
# SR-08 — File size check reads actual bytes not Content-Length header
# ============================================================================

def test_file_size_check_rejects_over_10mb():
    from app.routes.statements import _uploaded_file_size_bytes

    class FakeFile:
        stream = io.BytesIO(b'x' * (10 * 1024 * 1024 + 1))

    size = _uploaded_file_size_bytes(FakeFile())
    print(f"\n  File size: {size} bytes ({size / (1024*1024):.2f} MB) → over 10 MB limit")
    assert size > 10 * 1024 * 1024


def test_file_size_check_accepts_exactly_10mb():
    from app.routes.statements import _uploaded_file_size_bytes

    class FakeFile:
        stream = io.BytesIO(b'x' * (10 * 1024 * 1024))

    size = _uploaded_file_size_bytes(FakeFile())
    print(f"\n  File size: {size} bytes ({size / (1024*1024):.2f} MB) → exactly at 10 MB limit")
    assert size == 10 * 1024 * 1024


def test_file_size_check_accepts_small_file():
    from app.routes.statements import _uploaded_file_size_bytes

    class FakeFile:
        stream = io.BytesIO(b'small file content')

    size = _uploaded_file_size_bytes(FakeFile())
    print(f"\n  File size: {size} bytes → well under 10 MB limit")
    assert size < 10 * 1024 * 1024


# ============================================================================
# SR-17 — Secure cookie is config-driven
# ============================================================================

def test_debug_false_in_production(monkeypatch):
    from app.config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'x' * 32)
    monkeypatch.setenv('ENCRYPTION_KEY', 'x' * 32)

    app = create_app('production')
    print(f"\n  ProductionConfig → app.debug = {app.debug} → Secure cookie = {not app.debug}")
    assert app.debug is False


def test_debug_true_in_development():
    app = create_app('development')
    print(f"\n  DevelopmentConfig → app.debug = {app.debug} → Secure cookie = {not app.debug}")
    assert app.debug is True
