import redis
from contextlib import contextmanager
from typing import Iterator, Optional
from sqlalchemy.sql.base import NO_ARG
from tornado.log import app_log
from tornado_models import MissingDatabaseSettingError, MissingFactoryError

class RedisMixin:
    _redis_session = None  # type: Optional[redis.Redis]
    settings = {}

    @contextmanager
    def redis_session(self) -> Iterator[redis.Redis]:
        session = None

        try:
            session = self._make_redis_session()

            yield session
        except Exception:
            raise
        finally:
            if session:
                session.close()

    def on_finish(self):
        next_on_finish = None

        try:
            next_on_finish = super(RedisMixin, self).on_finish
        except AttributeError:
            pass

        if self._redis_session:
            self._redis_session.close()

        if next_on_finish:
            next_on_finish()

    @property
    def redis_conn(self) -> redis.Redis:
        if not self._redis_session:
            self._redis_session = self._make_redis_session()
        return self._redis_session

    def _make_redis_session(self) -> redis.Redis:
        if not self.settings:
            raise MissingFactoryError()
        redis = self.settings.get('redis')
        if not redis:
            raise MissingDatabaseSettingError()
        return redis.session

class Redis:
    def __init__(
        self, pool_options=None
    ):
        self.configure(
            pool_options=pool_options,
        )

    def configure(
        self, pool_options=None
    ):
        self.redis_pool = redis.ConnectionPool(**(pool_options or {}))

    @property
    def session(self):
        return self.get_session(pool=self.redis_pool)

    def get_session(self, pool=None):
        if not pool:
            raise MissingDatabaseSettingError()
        return redis.Redis(connection_pool=pool)
