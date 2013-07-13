__version__ = '0.11.0'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jinja2 import Environment, FileSystemLoader

def initialize(config=None, secrets=None, machine=None):
    """
    Build the giotto settings object. This function gets called
    at the very begining of every request cycle.
    """
    import giotto
    setattr(giotto, '_config', config)

    if secrets:
        for item in dir(secrets):
            s_value = getattr(secrets, item)
            setattr(giotto._config, item, s_value)

    if machine:
        for item in dir(machine):
            s_value = getattr(machine, item)
            setattr(giotto._config, item, s_value)

    db_engine = get_config("db_engine", None)
    if db_engine:
        # no engine directly added through config.
        # build from other settings
        etype = get_config("db_type")
        if etype == "sqlite3":
            try:
                from sqlite3 import dbapi2 as sqlite
            except ImportError:
                raise ImportError("You must install sqlite adapter: pip install sqlite3")

            db_name = get_config("db_name", "sqlite3.db")
            db_engine = create_engine('sqlite+pysqlite:///%s' % db_name, module=sqlite)
        if etype == "postgresql":
            db_name = get_config("db_name", "giotto")
            port = get_config("db_port", 5433)
            host = get_config("db_port", "localhost")
            username = get_config("db_username", "postgres")
            password = get_config("db_password", "")
            e = 'postgresql://%s:%s@%s:%s/%s' % (
                username, password, host, port, db_name
            )
            db_engine = create_engine(e)
        else:
            raise TypeError("Engine not supported: %s" % etype)
    
    if db_engine:
        setattr(giotto._config, "db_engine", db_engine)
        setattr(giotto._config, "db_session", sessionmaker(bind=db_engine)())

    auth_engine = get_config("auth_engine", None)
    if hasattr(auth_engine, 'lower'):
        # session engine was passed in as string, exchange for engine object.
        e = switchout_keyvalue(auth_engine)
        setattr(giotto._config, "auth_engine", e)

    cache_engine = get_config("cache_engine", None)
    if hasattr(cache_engine, 'lower'):
        # session engine was passed in as string, exchange for engine object.
        e = switchout_keyvalue(cache_engine)
        setattr(giotto._config, "cache_engine", e)

    td = get_config('jinja2_template_dir', None)
    if td:
        pp = get_config('project_path')
        e = Environment(loader=FileSystemLoader(os.path.join(pp, 'html')))
        setattr(giotto._config, "jinja2_env", e)

    
    

def get_config(item, default=None):
    """
    Use this function to get values from the config object.
    """
    import giotto
    return getattr(giotto._config, item, default) or default

def switchout_keyvalue(engine):
    if engine == 'dummy':
        return giotto.keyvalue.DummyKeyValue
    if engine == 'locmem':
        return giotto.keyvalue.LocMemKeyValue
    if engine == 'database':
        return giotto.keyvalue.DatabaseKeyValue
    if engine == 'memcached':
        return giotto.keyvalue.MemcacheKeyValue
    if engine == 'redis':
        return giotto.keyvalue.RedisKeyValue()