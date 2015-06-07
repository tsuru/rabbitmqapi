from __future__ import unicode_literals

import hmac
import hashlib

from flask import current_app


def generate_password(instance_name, app_host):
    """Generate a password for a RabbitMQ user"""
    hm = hmac.new(current_app.config['SALT'].encode('utf-8'), digestmod=hashlib.sha1)
    hm.update(instance_name.encode('utf-8'))
    hm.update(app_host.encode('utf-8'))
    return hm.hexdigest()


def generate_username(instance_name, app_host):
    """Generate a username to be created in RabbitMQ"""
    return '{}_{}_{}'.format(instance_name[:20], app_host[:20], generate_password(instance_name, app_host)[:10])
