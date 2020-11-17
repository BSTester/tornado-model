import multiprocessing
import redis
from concurrent.futures import Executor, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Callable, Iterator, Optional
from sqlalchemy.sql.base import NO_ARG
from tornado.concurrent import Future, chain_future
from tornado.ioloop import IOLoop
from tornado.web import Application

__all__ = ('as_future', 'RedisMixin', 'set_max_workers', 'Redis')


class MissingFactoryError(Exception):
    pass


class MissingDatabaseSettingError(Exception):
    pass


class _AsyncExecution:
    """Tiny wrapper around ThreadPoolExecutor. This class is not meant to be
    instantiated externally, but internally we just use it as a wrapper around
    ThreadPoolExecutor so we can control the pool size and make the
    `as_future` function public.
    """

    def __init__(self, max_workers: Optional[int] = None):
        self._max_workers = (
            max_workers or multiprocessing.cpu_count()
        )  # type: int
        self._pool = None  # type: Optional[Executor]

    def set_max_workers(self, count: int):
        if self._pool:
            self._pool.shutdown(wait=True)

        self._max_workers = count
        self._pool = ThreadPoolExecutor(max_workers=self._max_workers)

    def as_future(self, query: Callable) -> Future:
        # concurrent.futures.Future is not compatible with the "new style"
        # asyncio Future, and awaiting on such "old-style" futures does not
        # work.
        #
        # tornado includes a `run_in_executor` function to help with this
        # problem, but it's only included in version 5+. Hence, we copy a
        # little bit of code here to handle this incompatibility.

        if not self._pool:
            self._pool = ThreadPoolExecutor(max_workers=self._max_workers)

        old_future = self._pool.submit(query)
        new_future = Future()  # type: Future

        IOLoop.current().add_future(
            old_future, lambda f: chain_future(f, new_future)
        )

        return new_future


class RedisMixin:
    _redis_session = None  # type: Optional[redis.Redis]
    application = None  # type: Optional[Application]
    config = None

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
    def redis_session(self) -> redis.Redis:
        if not self._redis_session:
            self._redis_session = self._make_redis_session()
        return self._redis_session

    def _make_redis_session(self) -> redis.Redis:
        if not self.application and self.config:
            raise MissingFactoryError()
        
        if self.application:
            redis = self.application.settings.get('redis')
        elif self.config:
            redis = self.config.get('redis')
        else:
            redis = None
        if not redis:
            raise MissingDatabaseSettingError()
        return redis.session


_async_exec = _AsyncExecution()

as_future = _async_exec.as_future

set_max_workers = _async_exec.set_max_workers


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
