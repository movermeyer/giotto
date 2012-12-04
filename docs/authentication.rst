.. _ref-authentication:

==============
Authentication
==============

There is an application within the contrib submodule called ``auth`` that handles authentication.
This application uses SQLAlchemy_ to store user data.

This ``User`` model stores two pieces of information: username and password.
The password is stored as an encrypted string.
Encrypting is done automatically by the bcrypt_ library.

This user class is not intended to store all information that an application developer would want to store for a user.
The developer is meant to create their own user profile table that connects to the User table via foreign key.

Enabling Authentication for your application
--------------------------------------------

All you need to do is import the login and registration programs into your application's ``programs.py`` file::

    from giotto.contrib.auth.programs import (
        UserRegistrationSubmit, UserRegistrationForm, LoginForm, LoginSubmit
    )

Then, to register a new account, point your browser to the ``register`` program.
Enter your username and password and click submit. This will create a new user in the system.
Usernames, by default have to conform to the following regex: ``^[\d\w]{4,30}$``.
This can be changed by adding a regex string to ``auth_regex`` in your project's config file.

To login, point your browser to the ``login`` program. Enter your credentials.
If the username/password you entered match a row int he user table, you will be logged in.

How Authentication works under the hood
---------------------------------------
When using the HTTP controller, loggin in sets two cookies, ``username`` and ``password``.
The password cookie is not a raw password. It is the hashed cookie, hashed by bcrypt.

To authenticate this username/password cookie,
add the ``AuthenticationMiddleware`` to the input_middleware stream of your program.
This middleware class will inspect the cookies, and add a ``user`` attribute to the request.
Requests coming through this middleware that aren't authenticated will result in a ``request.user`` value that is ``None``.

To access the authenticated user from within ght model, use the LOGGED_IN_USER primitive::

    from giotto.primitives import LOGGED_IN_USER

    def some_model_function(user=LOGGED_IN_USER):
        return {'user': user}

If the program is accessed by a logged in uer,
the value of ``LOGGED_IN_USER`` will be the User object that corresponds to the currently logged in user.
If the program is accessed by a non-logged in user, ``LOGGED_IN_USER`` will be ``None``.

Another middleware class, ``SetAuthenticationCookie`` is put in the output middleware stream.
It's job is to set the cookies so each subsequent request can be authenticated.
By default, the authentication cookie expires after 30 days.
This value can be changed by setting the ``auth_cookie_expire`` value to the number of hours the cookie shoudl live for,
in your project's ``config.py``.

Extending the views on the login/register programs
--------------------------------------------------

To extend the way the default login looks, subclass the program with your own view defined::

    class MyLogin(LoginForm):
        view = MyLoginView

    class MyRegisterForm(UserRegistrationForm):
        view = MyRegisterView

or by defining the whole program yourself::

    class LoginForm(GiottoProgram):
        name = 'login'
        controllers = ('http-get', )
        model = []
        view = MyRegisterView

.. _SQLAlchemy: http://www.sqlalchemy.org/
.. _bcrypt: http://www.mindrot.org/projects/py-bcrypt/