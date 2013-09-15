import pickle
import re
import bcrypt

from django.db import models

class DBKeyValueManager(models.Manager):
    def cache_set(self, key, obj, expire):
        when_expire = datetime.datetime.now() + datetime.timedelta(seconds=expire)
        new = cls(key=key, value=pickle.dumps(obj), expires=when_expire)

    def cache_get(self, key):
        try:
            hit = DBKeyValue.objects.get(key=key, expires__gt=datetime.datetime.now())
            return pickle.loads(str(hit.value))
        except DBKeyValue.DoesNotExist:
            return None

class DBKeyValue(models.Model):
    key = models.TextField(primary_key=True)
    value = models.TextField()
    expires = models.DateTimeField()

    objects = DBKeyValueManager()

class UserManager(models.Manager):
    def get_user_by_password(self, username, password):
        """
        Given a username and a raw, unhashed password, get the corresponding
        user, retuns None if no match is found.
        """
        try:
            user = self.get(username=username)
        except User.DoesNotExist:
            return None
        
        if bcrypt.hashpw(password, user.password) == user.password:
            return user
        else:
            return None

    def get_user_by_hash(self, username, hash):
        return self.get(username=username, password=hash)


class User(models.Model):
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
        if get_config('db_session').query(User).filter_by(username=self.username).first():
            errors['username'] = {'message': 'Username already exists', 'value': self.username}

        if errors:
            raise InvalidInput("User data not valid", **errors)

    @classmethod
    def create(cls, username, password):
        """
        Create a new user instance
        """
        user = cls(username=username, password=password)
        user.validate()
        session = get_config('db_session')
        session.add(user)
        session.commit()
        return user

    @classmethod
    def all(cls):
        return get_config('db_session').query(cls).all()

    def __repr__(self):
        return "<User('%s', '%s')>" % (self.username, self.password)