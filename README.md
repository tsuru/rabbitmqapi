# tsuru-rabbitmqapi

[![Build Status](https://travis-ci.org/qdqmedia/rabbitmqapi.png?branch=master)](https://travis-ci.org/qdqmedia/rabbitmqapi)
[![Coverage Status](https://coveralls.io/repos/qdqmedia/rabbitmqapi/badge.png?branch=master)](https://coveralls.io/r/qdqmedia/rabbitmqapi?branch=master)

This API exposes a [RabbitMQ](https://www.rabbitmq.com) service to application developers using [Tsuru](https://tsuru.io) PaaS.

Please note that you need a working Tsuru installation in order to use this software. Installation of Tsuru itself is not covered here.

Development was sponsored by [QDQ Media, S.A.U.](https://qdqmedia.com) which uses Tsuru as part of its infrastructure.

## RabbitMQ Installation

If you don't have a working RabbitMQ instance, you should configure one. In Debian/Ubuntu, you can use `apt-get` to do it.

```bash
$ sudo apt-get install rabbitmq-server
```

After installing RabbitMQ, you need to create an administrative user which will be used by the service to interact
with the [RabbitMQ Management HTTP API](https://cdn.rawgit.com/rabbitmq/rabbitmq-management/master/priv/www/api/index.html).

```bash
$ ADMIN_PASSWORD=$(openssl rand -hex 20); echo $ADMIN_PASSWORD
$ sudo rabbitmqctl add_user admin $ADMIN_PASSWORD
$ sudo rabbitmqctl set_user_tags admin administrator
$ sudo rabbitmqctl set_permissions -p / admin ".*" ".*" ".*"
```

You may also want to delete the `guest` admin user which might be created automatically by the Debian/Ubuntu package:
  
```bash
$ sudo rabbitmqctl delete_user guest
```

If you wish, you can enable the RabbitMQ web management interface to inspect the state of your instance
 
```bash
$ sudo rabbitmq-plugins enable rabbitmq_management
```

The web interface listens on `http://<rabbitmqhost>:15672`. You can log in with the credentials `admin` / `$ADMIN_PASSWORD` 

Please refer to [RabbitMQ documentation](https://www.rabbitmq.com/admin-guide.html) for more information
regarding the configuration and management of the server.

## Install the service in Tsuru

The suggested way is to have the rabbitmqapi service running as a Tsuru application.

Let's create the Tsuru app:

```bash
$ git clone https://github.com/qdqmedia/rabbitmqapi.git
$ cd rabbitmqapi
$ tsuru app-create rabbitmqapi python
# The following is used by the user provisioning machinery
$ tsuru env-set RMQAPI_SALT=$(openssl rand -hex 20)  
# These are the credentials used to talk with RabbitMQ. Replace <rabbitmqhost> with the host of your RabbitMQ instance
$ tsuru env-set RMQAPI_RMQ_HOST=<rabbitmqhost> RMQAPI_RMQ_USER=admin RMQAPI_RMQ_PASSWORD=$ADMIN_PASSWORD
# These are the credentials Tsuru uses to authenticate against the service
$ TSURU_SERVICE_PASSWORD=$(openssl rand -hex 20); echo $TSURU_SERVICE_PASSWORD
$ tsuru env-set RMQAPI_USERNAME=tsuru RMQAPI_PASSWORD=$TSURU_SERVICE_PASSWORD
# Put the service online
$ tsuru app-info | grep Repository
$ git remote add tsuru git@<tsururepo>:rabbitmqapi.git # see above command for the URL
$ git push tsuru master
```

At this point you can check if the communication with rabbitmq works correctly:

```bash
$ tsuru app-info | grep Address # find out the service address
# create a new instance
$ curl -utsuru:$TSURU_SERVICE_PASSWORD -XPOST -d "name=testservice" http://<rabbitmqapihost>/resources
# ping it, it should return a 204 HTTP status code.
$ curl -i -utsuru:$TSURU_SERVICE_PASSWORD http://<rabbitmqapihost>/resources/testservice/status
# delete it
$ curl -utsuru:$TSURU_SERVICE_PASSWORD -XDELETE http://<rabbitmqapihost>/resources/testservice
```

Now, configure Tsuru to make the service available to your users:

```bash
$ cp manifest.yaml.example manifest.yaml
# you can find out production address from app-info
$ tsuru app-info | grep Address
# set production address, username and password. User and password correspond to $TSURU_SERVICE_USER and $TSURU_SERVICE_PASSWORD
$ vim manifest.yaml
$ crane create manifest.yaml
```

At this point you should see your service up and available to your users:

```bash
$ tsuru service-list
```

# Development

rabbitmqapi is a [Flask](http://flask.pocoo.org/) web aplication which uses the
[RabbitMQ Management HTTP API](https://cdn.rawgit.com/rabbitmq/rabbitmq-management/master/priv/www/api/index.html) and 
implements the [Tsuru service workflow](http://docs.tsuru.io/en/latest/services/api.html). Contributions are welcome.

## Tests

Install the `tox` package and run tests with `tox`. Tests will run against Python 2.7 & 3.4.

## Running outside of tsuru

You can run the API outside of Tsuru for development purposes. To do this, you need to export a few environment variables
(which in production are exposed by Tsuru itself). Please note that you still need a running RabbitMQ instance.

```bash
$ export RMQAPI_RMQ_HOST=<rabbitmqhost> RMQAPI_RMQ_USER=admin RMQAPI_RMQ_PASSWORD=$ADMIN_PASSWORD RMQAPI_SALT=$(openssl rand -hex 20)`
$ export RMQAPI_USERNAME=tsuru RMQAPI_PASSWORD=$TSURU_SERVICE_PASSWORD`
$ flask --app=rabbitmqapi.app --debug run --reload  
```
You can test the various API endpoints described in the [Tsuru service workflow](http://docs.tsuru.io/en/latest/services/api.html):

* Create a service:
```bash
curl -utsuru:$TSURU_SERVICE_PASSWORD -XPOST -d "name=testservice" http://localhost:5000/resources
```

* Delete it
````bash
curl -utsuru:$TSURU_SERVICE_PASSWORD -XDELETE http://localhost:5000/resources/testservice
```

* Bind app to service
```bash
curl -utsuru:$TSURU_SERVICE_PASSWORD -XPOST -d "app-host=tsuru01" http://localhost:5000/resources/testservice/bind-app
```

* Delete service-app binding
```bash
curl -utsuru:$TSURU_SERVICE_PASSWORD -XDELETE -d "app-host=tsuru01" http://localhost:5000/resources/testservice/bind-app
```

* Health check
```bash
curl -utsuru:$TSURU_SERVICE_PASSWORD http://localhost:5000/resources/testservice/status
```

## TODO

- [ ] Do not allow `delete_instance` if queues are present
- [ ] Dedicated instances
