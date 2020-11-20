# tornado-models

sqlalchemy and redis for tornado

## Installation

    pip install tornado-models

## Usage

### sqlalchemy

```
from tornado.web import Application
from tornado_models.sqlalchemy import SQLAlchemy

from my_app.handlers import IndexHandler

app = Application(
    ((r'/', IndexHandler),),
    db=SQLAlchemy(database_url)
 )

##################################

from tornado_models.sqlalchemy import SQLAlchemy

db = SQLAlchemy(url=database_url)

class User(db.Model):
    id = Column(BigInteger, primary_key=True)
    username = Column(String(255), unique=True)

##################################

from tornado_models.sqlalchemy import SessionMixin
from tornado_models import as_future

class NativeCoroutineRequestHandler(SessionMixin, RequestHandler):
    async def get(self):
        with self.db_session() as session:
            count = await as_future(session.query(User).count())

        self.write('{} users so far!'.format(count))
```

### redis

```
from tornado.web import Application
from tornado_models.redis import Redis

from my_app.handlers import IndexHandler

app = Application(
    ((r'/', IndexHandler),),
    redis=Redis(pool_options(dict(host='localhost', port=6379, db=0)))
 )

##################################

from tornado_models.redis import RedisMixin
from tornado_models import as_future

class NativeCoroutineRequestHandler(RedisMixin, RequestHandler):
    async def get(self):
        with self.redis_session() as session:
            value = await as_future(session.get('key'))

        self.write('redis value is {}!'.format(value))
```

[Demo Project](https://github.com/BSTester/OpenStark)

[https://tornado-sqlalchemy.readthedocs.io/en/stable/](https://tornado-sqlalchemy.readthedocs.io/en/stable/)