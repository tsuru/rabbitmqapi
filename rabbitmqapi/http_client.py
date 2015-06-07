from __future__ import unicode_literals

import requests

from flask import abort, current_app


def send(verb, rel_url, raise_for_status=True, *request_args, **requests_kwargs):
    """
    Thin wrapper around requests which takes care of setting up default params needed to talk with the RabbitMQ API.

    If a non-recoverable error occurs while talking to RabbitMQ, we propagate an HTTP error.
    """
    verb = getattr(requests, verb)
    rmq_base_url = 'http://{host}:{port}/api'.format(
        host=current_app.config['RMQ_HOST'],
        port=current_app.config['RMQ_MGMT_PORT']
    )
    try:
        response = verb(
            '{}/{}'.format(rmq_base_url, rel_url),
            *request_args,
            auth=(current_app.config['RMQ_USER'], current_app.config['RMQ_PASSWORD']),
            headers={'Content-Type': 'application/json'},
            timeout=5,
            **requests_kwargs
        )
    except requests.RequestException as e:
        return abort(500, str(e))

    if raise_for_status:
        try:
            response.raise_for_status()
        except requests.HTTPError:
            return abort(500, 'Error, rabbitmq returned status code {}'.format(response.status_code))

    return response
