from __future__ import unicode_literals

import os
import json
import unittest
import base64
import tempfile
from mock import patch

import pep8
import requests
import responses
from werkzeug.exceptions import InternalServerError


from . import create_app
from .api import log_request, ha_policy_name
from .http_client import send
from .auth import requires_auth
from .utils import generate_username, generate_password

from flask import Flask, Response

CONFIG = dict(
    USERNAME='foo',
    PASSWORD='bar',
    RMQ_HOST='example.com',
    RMQ_USER='foo',
    RMQ_PASSWORD='bar',
    SALT='foooosalt',
    RMQ_PORT=6672,
    RMQ_MGMT_PORT=15672,
)
app = create_app()
app.config.from_mapping(CONFIG)


class AppFactoryTest(unittest.TestCase):
    def test_appfactory(self):
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(b'FOO=1')
            tmp.flush()
            app1 = create_app(tmp.name)
            self.assertEqual(app1.config['FOO'], 1)


class PEP8Test(unittest.TestCase):
    def test_pep8_conformance(self):
        """Test that we conform to PEP8."""
        source_files = []
        package_dir = os.path.dirname(os.path.abspath(__file__))

        for root, directories, filenames in os.walk(package_dir):
            source_files.extend([os.path.join(root, f) for f in filenames if f.endswith('.py')])

        pep8style = pep8.StyleGuide(quiet=False, max_line_length=120)
        result = pep8style.check_files(source_files)
        self.assertEqual(result.total_errors, 0,
                         "Found code style errors (and warnings). "
                         "Run pep8 --max-line-length=120 *.py for details")


class AuthTest(unittest.TestCase):
    def test_auth(self):
        @requires_auth
        def myview():
            return Response('', 200)

        #
        # Test a forbidden response (access without credentials to a protected view)
        #
        with app.test_request_context('/testauth'):
            response = myview()
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.data, b'Login Required')
            self.assertTrue(
                set({'WWW-Authenticate': 'Basic realm="Login Required"'}.items()).issubset(response.headers.items())
            )

        #
        # Test a correctly authenticated request
        #
        api_credentials = base64.b64encode(
            "{0}:{1}".format(app.config['USERNAME'], app.config['PASSWORD']).encode('utf-8')
        )
        auth_headers = {
            'Authorization': 'Basic {}'.format(api_credentials.decode('utf-8'))
        }
        with app.test_request_context('/testauth', headers=auth_headers):
            response = myview()
            self.assertEqual(response.status_code, 200)


class RequestDebuggingTest(unittest.TestCase):
    def test_requestdebugging(self):

        custom_app = Flask(__name__)
        custom_app.before_request(log_request)

        @custom_app.route('/foo')
        def foo():
            return ''

        with custom_app.test_request_context('/foo'):
            with custom_app.test_client() as client:
                with patch('flask.current_app.logger.debug') as mocked_debug:
                    client.get('/foo')

        self.assertEqual(mocked_debug.call_count, 1)


class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.rmq_base_url = 'http://{host}:{port}/api'.format(
            host=app.config['RMQ_HOST'],
            port=app.config['RMQ_MGMT_PORT']
        )

    @responses.activate
    def test_send(self):
        with app.app_context():

            responses.add(responses.GET, '{}/foo1'.format(self.rmq_base_url), status=200)
            self.assertEqual(send('get', 'foo1').status_code, 200)

            #
            # timeouts and other requests errors
            #
            def callback(request):
                raise requests.RequestException('Requests exception')
            responses.add_callback(
                responses.GET, '{}/foo2'.format(self.rmq_base_url), callback=callback,
            )
            with self.assertRaises(InternalServerError):
                send('get', 'foo2')

            #
            # Test non-200 resposes with raise_for_status=True
            #
            responses.add(
                responses.GET, '{}/foo3'.format(self.rmq_base_url), status=400,
            )
            with self.assertRaises(InternalServerError):
                send('get', 'foo3')

            #
            # Test that we return a resposes with raise_for_status=False
            #
            responses.add(
                responses.GET, '{}/foo4'.format(self.rmq_base_url), status=400,
            )
            response = send('get', 'foo4', raise_for_status=False)
            self.assertEqual(response.status_code, 400)


class ApiTest(unittest.TestCase):

    def assertSameJSON(self, json1, json2):
        """Tells whether two json strings, once decoded, are the same dictionary"""
        return self.assertDictEqual(json.loads(json1), json.loads(json2))

    def setUp(self):
        self.app = app.test_client()
        api_credentials = base64.b64encode(
            "{0}:{1}".format(app.config['USERNAME'], app.config['PASSWORD']).encode('utf-8')
        )
        self.auth_headers = {
            'Authorization': 'Basic {}'.format(api_credentials.decode('utf-8'))
        }
        self.rmq_base_url = 'http://{host}:{port}/api'.format(
            host=app.config['RMQ_HOST'],
            port=app.config['RMQ_MGMT_PORT']
        )

    def test_plans(self):
        response = self.app.get('/resources/plans')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), json.dumps([]))

    @responses.activate
    def test_add_instance(self):
        #
        # Test missing `naame` argument
        #
        response = self.app.post('/resources', headers=self.auth_headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, b'Error, missing name argument')

        #
        # Test correct creation of a Vhost in HA
        #
        responses.add(
            responses.PUT,
            '{}/vhosts/foobar'.format(self.rmq_base_url),
            status=200,
        )

        responses.add(
            responses.PUT,
            '{base_url}/permissions/foobar/{username}'.format(
                base_url=self.rmq_base_url, username=app.config['RMQ_USER']),
            status=200,
        )

        responses.add(
            responses.PUT,
            '{base_url}/policies/foobar/{policy_name}'.format(
                base_url=self.rmq_base_url, policy_name=ha_policy_name),
            status=200,
        )

        response = self.app.post('/resources', data={'name': 'foobar'}, headers=self.auth_headers)
        self.assertEqual(response.status_code, 201)
        responses.reset()

        #
        # Test Rollback when creating a vhost, adding an admin fails to that vhost
        #
        responses.add(
            responses.PUT,
            '{}/vhosts/foobar'.format(self.rmq_base_url),
            status=200,
        )

        responses.add(
            responses.PUT,
            '{base_url}/permissions/foobar/{username}'.format(
                base_url=self.rmq_base_url, username=app.config['RMQ_USER']),
            status=400,
        )

        responses.add(
            responses.DELETE,
            '{}/vhosts/foobar'.format(self.rmq_base_url),
            status=200,
        )

        response = self.app.post('/resources', data={'name': 'foobar'}, headers=self.auth_headers)
        self.assertEqual(response.status_code, 500)
        self.assertTrue('Error, rabbitmq returned status code 400' in response.get_data(as_text=True))
        responses.reset()

        #
        # Test Rollback when creating a vhost, adding HA policy fails
        #
        responses.add(
            responses.PUT,
            '{}/vhosts/foobar'.format(self.rmq_base_url),
            status=200,
        )

        responses.add(
            responses.PUT,
            '{base_url}/permissions/foobar/{username}'.format(
                base_url=self.rmq_base_url, username=app.config['RMQ_USER']),
            status=200,
        )

        responses.add(
            responses.PUT,
            '{base_url}/policies/foobar/{policy_name}'.format(
                base_url=self.rmq_base_url, policy_name=ha_policy_name),
            status=400,
        )

        responses.add(
            responses.DELETE,
            '{}/vhosts/foobar'.format(self.rmq_base_url),
            status=200,
        )

        response = self.app.post('/resources', data={'name': 'foobar'}, headers=self.auth_headers)
        self.assertEqual(response.status_code, 500)
        self.assertTrue('Error, rabbitmq returned status code 400' in response.get_data(as_text=True))

    @responses.activate
    def test_delete_instance(self):
        responses.add(
            responses.DELETE,
            '{}/vhosts/foobar'.format(self.rmq_base_url),
            status=200
        )
        response = self.app.delete('/resources/foobar', headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_bind_app(self):
        #
        # Test missing app-host
        #
        response = self.app.post('/resources/foobar/bind-app', headers=self.auth_headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, b'Parameter `app-host` is empty')

        with app.app_context():
            rmq_new_user, rmq_new_password = \
                generate_username('foobar', 'domain.example.com'),\
                generate_password('foobar', 'domain.example.com')
        #
        # Test when users and permissions are created correctly
        #
        responses.add(
            responses.PUT,
            '{}/users/{}'.format(self.rmq_base_url, rmq_new_user),
            status=200,
        )
        responses.add(
            responses.PUT,
            '{}/permissions/foobar/{}'.format(self.rmq_base_url, rmq_new_user),
            status=200,
        )
        response = self.app.post('/resources/foobar/bind-app',
                                 headers=self.auth_headers,
                                 data={'app-host': 'domain.example.com'})

        self.assertEqual(response.status_code, 201)
        self.assertSameJSON(response.get_data(as_text=True), json.dumps(dict(
            RABBITMQ_HOST=app.config['RMQ_HOST'],
            RABBITMQ_PORT=str(app.config['RMQ_PORT']),
            RABBITMQ_VHOST='foobar',
            RABBITMQ_USERNAME=rmq_new_user,
            RABBITMQ_PASSWORD=rmq_new_password,
        )))
        responses.reset()
        #
        # Test when we have to rollback the creation of a user
        #
        responses.add(
            responses.PUT,
            '{}/users/{}'.format(self.rmq_base_url, rmq_new_user),
            status=200,
        )
        responses.add(
            responses.PUT,
            '{}/permissions/foobar/{}'.format(self.rmq_base_url, rmq_new_user),
            status=400,
        )
        responses.add(
            responses.DELETE,
            '{}/users/{}'.format(self.rmq_base_url, rmq_new_user),
            status=200,
        )
        response = self.app.post('/resources/foobar/bind-app',
                                 headers=self.auth_headers,
                                 data={'app-host': 'domain.example.com'})
        self.assertEqual(response.status_code, 500)
        self.assertTrue('Error, rabbitmq returned status code 400' in response.get_data(as_text=True))

    @responses.activate
    def test_unbind_app(self):
        #
        # Test missing app-host
        #
        response = self.app.delete('/resources/foobar/bind-app', headers=self.auth_headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, b'Parameter `app-host` is empty')

        with app.app_context():
            username = generate_username('foobar', 'domain.example.com')

        responses.add(
            responses.DELETE,
            '{}/users/{}'.format(self.rmq_base_url, username),
            status=200,
        )
        response = self.app.delete('/resources/foobar/bind-app',
                                   headers=self.auth_headers,
                                   data={'app-host': 'domain.example.com'})
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_bind_unit(self):
        # This just tests a stub
        response = self.app.post('/resources/foobar/bind',
                                 headers=self.auth_headers)
        self.assertEqual(response.status_code, 201)

    @responses.activate
    def test_unbind_unit(self):
        # This just tests a stub
        response = self.app.delete('/resources/foobar/bind',
                                   headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_status(self):
        #
        # Test succesffull operation
        #
        responses.add(
            responses.GET,
            '{}/aliveness-test/foobar1'.format(self.rmq_base_url),
            status=200,
            body='''{"status": "ok"}''',
            content_type='application/json'
        )
        response = self.app.get('/resources/foobar1/status',
                                headers=self.auth_headers)
        self.assertEqual(response.status_code, 204)

        #
        # Test Invalid JSON returned by rabbitmq
        #
        responses.add(
            responses.GET,
            '{}/aliveness-test/foobar2'.format(self.rmq_base_url),
            status=200,
            body='''{"status":}''',
            content_type='application/json'
        )
        response = self.app.get('/resources/foobar2/status',
                                headers=self.auth_headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data,
                         b'''Error pinging service, malformed response from rabbitmq, content: {"status":}''')

        #
        # Test Invalid JSON returned by rabbitmq
        #
        responses.add(
            responses.GET,
            '{}/aliveness-test/foobar3'.format(self.rmq_base_url),
            status=200,
            body='''{"status":}''',
            content_type='application/json'
        )
        response = self.app.get('/resources/foobar3/status', headers=self.auth_headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data,
                         b'''Error pinging service, malformed response from rabbitmq, content: {"status":}''')

        #
        # Test malformed rabbitmq response, missing status key
        #
        responses.add(
            responses.GET,
            '{}/aliveness-test/foobar4'.format(self.rmq_base_url),
            status=200,
            body='''{"foobar":"ok"}''',
            content_type='application/json'
        )
        response = self.app.get('/resources/foobar4/status', headers=self.auth_headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data,
                         b'''Error pinging service, malformed response from rabbitmq, content: {"foobar":"ok"}''')
        #
        # Test rabbitmq response with status not 'ok'
        #
        responses.add(
            responses.GET,
            '{}/aliveness-test/foobar5'.format(self.rmq_base_url),
            status=200,
            body='''{"status":"ko"}''',
            content_type='application/json'
        )
        response = self.app.get('/resources/foobar5/status', headers=self.auth_headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data,
                         b'''Error pinging rabbitmq, content: {"status":"ko"}''')

if __name__ == '__main__':
    unittest.main()
