import re
import bcrypt

from giotto.exceptions import InvalidInput
from giotto.utils import random_string
from giotto.primitives import LOGGED_IN_USER
from giotto import get_config
from django.db import models

class BasicUser(models.Model):
    username = models.TextField(primary_key=True)
    password = models.TextField()

    def __init__(self, username, password):
        self.username = username
        hashed = ''
        if not password == '':
            # skip hashing process if the password field is left blank
            # helpful for creating mock user objects without slowing things down.
            hashed = bcrypt.hashpw(password, bcrypt.gensalt())
        self.password = hashed
        self.raw_password = password
    
    def validate(self):
        """
        Make sure this newly created user instance meets the username/password
        requirements
        """
        r = get_config('auth_regex', r'^[\d\w]{4,30}$')
        errors = {}
        if not re.match(r, self.username):
            errors['username'] = {'message': 'Username not valid', 'value': self.username}
        if len(self.raw_password) < 4:
            errors['password'] = {'message': 'Password much be at least 4 characters'}
        if User.objects.filter(username=self.username).exists():
            errors['username'] = {'message': 'Username already exists', 'value': self.username}

        if errors:
            raise InvalidInput("User data not valid", **errors)

    @classmethod
    def get_user_by_password(cls, username, password):
        """
        Given a username and a raw, unhashed password, get the corresponding
        user, retuns None if no match is found.
        """
        user = cls.objects.get(username=username)

        if bcrypt.hashpw(password, user.password) == user.password:
            return user
        else:
            return None

    @classmethod
    def get_user_by_hash(cls, username, hash):
        return cls.objects.get(username=username, password=hash)

    @classmethod
    def create(cls, username, password):
        """
        Create a new user instance
        """
        user = cls(username=username, password=password)
        user.validate()
        user.save()
        return user

    def __repr__(self):
        return "<User('%s', '%s')>" % (self.username, self.password)


def basic_register(username, password, password2):
    """
    Register a user and session, and then return the session_key and user.
    """
    if password != password2:
        raise InvalidInput(password={'message': "Passwords do not match"},
                           username={'value': username})
    user = User.create(username, password)
    return create_session(user.username, password)

def create_session(username, password):
    """
    Create a session for the user, and then return the key.
    """
    user = User.get_user_by_password(username, password)
    auth_session_engine = get_config('auth_session_engine')
    if not user:
        raise InvalidInput('Username or password incorrect')
    session_key = random_string(15)
    while auth_session_engine.get(session_key):
        session_key = random_string(15)
    auth_session_engine.set(session_key, user.username, get_config('auth_session_expire'))
    return {'session_key': session_key, 'user': user}