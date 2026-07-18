from flask import Flask, jsonify
from flask_limiter import Limiter
from app.config import config
from app.extensions import db, cors
from app.utils.request_meta import client_ip
from werkzeug.exceptions import HTTPException


limiter = Limiter(key_func=client_ip, default_limits=[])



def create_app(config_name='development'):
    app = Flask(__name__)
    selected_config = config[config_name]
    if hasattr(selected_config, 'validate'):
        selected_config.validate()
    app.config.from_object(selected_config)

    db.init_app(app)
    cors.init_app(app, origins=app.config['FRONTEND_URL'], supports_credentials=True)
    limiter.init_app(app)
    if app.config.get('TESTING'):
        app.config['CSRF_PROTECTION_ENABLED'] = False

    from app.middleware.csrf import register_csrf_protection
    from app.middleware.security_headers import register_security_headers

    register_csrf_protection(app)
    register_security_headers(app)

    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.users import users_bp
    from app.routes.statements import statements_bp
    from app.routes.transactions import transactions_bp
    from app.routes.categories import categories_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.consents import consents_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(statements_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(consents_bp)
    app.register_blueprint(admin_bp)

    def _json_error(message, status_code):
        return jsonify(error=message), status_code

    @app.errorhandler(HTTPException)
    def http_error(e):
        messages = {
            400: 'Bad request',
            401: 'Unauthorised',
            403: 'Forbidden',
            404: 'Not found',
            405: 'Method not allowed',
            413: 'File too large',
            415: 'Unsupported file type',
            429: 'Too many requests',
        }
        return _json_error(messages.get(e.code, 'Request failed'), e.code)

    @app.errorhandler(Exception)
    def internal_error(e):
        app.logger.exception('Unhandled server error')
        return _json_error('Internal server error', 500)

    return app
