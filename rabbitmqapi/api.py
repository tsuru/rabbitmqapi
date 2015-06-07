from __future__ import unicode_literals

import json

from flask import Blueprint, current_app, request, jsonify, abort

from .http_client import send
from .auth import requires_auth
from .utils import generate_username, generate_password


api = Blueprint('api', __name__)

#
# User permissions
#
full_permissions = {"configure": ".*", "write": ".*", "read": ".*"}


def log_request():
    """Debug incoming requests, useful to debug tsuru incoming calls"""
    current_app.logger.debug('Got request: {request}\n{headers}{body}'.format(
        request=str(request), headers=request.headers, body=request.get_data()
    ))


# we don't use the decorator form to leave the log_request function intact and unit-test it more cleanly
api.before_request(log_request)


@api.route("/resources", methods=["POST"])
@requires_auth
def add_instance():
    """create a new instance of the service. This translates to a new vhost in RabbitMQ"""

    if 'name' not in request.form:
        return 'Error, missing name argument', 400

    send('put', 'vhosts/{name}'.format(name=request.form['name']))
    return '', 201


@api.route("/resources/<name>", methods=["DELETE"])
@requires_auth
def delete_instance(name):
    """delete a new instance of the service. This translates to removing a vhost in RabbitMQ"""

    send('delete', 'vhosts/{name}'.format(name=name))
    return '', 200


@api.route("/resources/<name>/bind-app", methods=["POST"])
@requires_auth
def bind_app(name):
    """
    Called every time an app adds an unit (container). This can be used to keep track of authentication details related
    to the ip address of a container.
    """
    app_host = request.form.get('app-host')
    if not app_host:
        return 'Parameter `app-host` is empty', 400

    username, password = generate_username(name, app_host), generate_password(name, app_host)

    # create the user
    send('put', 'users/{username}'.format(username=username), data=json.dumps({"password": password, "tags": ""}))
    permissions_granted = send(
        'put', 'permissions/{instance_name}/{username}'.format(username=username, instance_name=name),
        data=json.dumps(full_permissions),
        raise_for_status=False
    )
    if not permissions_granted.ok:
        send('delete', 'users/{username}'.format(username=username))
        return abort(500, 'Error, rabbitmq returned status code {}'.format(permissions_granted.status_code))

    return jsonify(
        RABBITMQ_HOST=current_app.config['RMQ_HOST'],
        RABBITMQ_PORT=str(current_app.config['RMQ_PORT']),
        RABBITMQ_VHOST=name,
        RABBITMQ_USERNAME=username,
        RABBITMQ_PASSWORD=password,
    ), 201


@api.route("/resources/<name>/bind-app", methods=["DELETE"])
@requires_auth
def unbind_app(name):
    app_host = request.form.get("app-host")
    if not app_host:
        return 'Parameter `app-host` is empty', 400
    username = generate_username(name, app_host)
    send('delete', 'users/{username}'.format(username=username))
    return "", 200


@api.route("/resources/<name>/status", methods=["GET"])
@requires_auth
def status(name):
    """check the status of the instance named <name>"""
    response = send('get', 'aliveness-test/{name}'.format(name=name))
    try:
        response_data = response.json()['status']
    except (ValueError, KeyError):
        return 'Error pinging service, malformed response from rabbitmq, content: {}'.format(
            response.text), 500

    if not (response_data == 'ok'):
        return 'Error pinging rabbitmq, content: {}'.format(response.text), 500

    return "", 204


#
# Stubs
#
@api.route("/resources/<name>/bind", methods=["POST"])
@requires_auth
def bind_unit(name):
    """
    Called every time an app adds an unit (container). This can be used to keep track of authentication details
    related to the ipaddress of a container.

    There seems to useful way to implement this function for now.
    """
    return '', 201


@api.route("/resources/<name>/bind", methods=["DELETE"])
@requires_auth
def unbind_unit(name):
    """
    Called every time an app adds an unit (container). This can be used to keep track of authentication details
    related to the ipaddress of a container.

    There seems to useful way to implement this function for now.
    """
    return '', 200


@api.route("/resources/plans", methods=["GET"])
def plans():
    """Placeholder until we figure out what plans we could expose."""
    #
    # Use dumps instead of jsonify to return a top level array, see
    # http://flask.pocoo.org/docs/0.10/security/#json-security
    # It is safe if we don't do any user-data processing.
    #
    return json.dumps([])
