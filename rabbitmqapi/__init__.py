from __future__ import unicode_literals

from flask import Flask
from .api import api


def create_app(cfg=None):
    """
    App factory, useful to instantiate the app from unit tests
    passing a custom configuration to it.

    :param cfg: a filename pointing to a valid python module to
                be used as a Flask configuration module.

    :returns: a Flask application
    """
    app = Flask(__name__)
    if cfg:
        app.config.from_pyfile(cfg)

    app.register_blueprint(api)
    return app
