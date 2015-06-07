from __future__ import unicode_literals

from functools import wraps
from flask import request, Response, current_app


def requires_auth(f):
    """Authenticate incoming requests against app.config['USERNAME'] and app.config['PASSWORD'] using HTTP basic auth"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == current_app.config['USERNAME'] and
                            auth.password == current_app.config['PASSWORD']):
            return Response('Login Required', 401,
                            {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated
