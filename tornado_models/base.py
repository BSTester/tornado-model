from sqlalchemy.ext.declarative import DeclarativeMeta
from tornado.web import RequestHandler
from tornado.log import app_log
from tornado_models.sqlalchemy import SessionMixin, SQLAlchemy
from tornado_models.redis import RedisMixin, Redis
from tornado_models import as_future
from xml.etree import cElementTree as ET
from munch import munchify
import functools
import json


# 异步用户认证
def authenticated_async(f):
    @functools.wraps(f)
    async def wrapper(self, *args, **kwargs):
        self._auto_finish = False
        self.current_user = await self.get_current_user_async()
        if self.current_user is None:
            self.set_status(401, 'Not Authorization')
            self.write_json(dict(success=False, code=401, message='登录超时, 请重新登录', showType=4, data=''))
        elif self.current_user is False:
            self.set_status(403, 'Forbidden')
            self.write_json(dict(success=False, code=403, message='禁止访问', showType=9, data=''))
        else:
            await f(self, *args, **kwargs)
    return wrapper


class BaseRequestHandler(RequestHandler, SessionMixin, RedisMixin):
    current_user = None

    def initialize(self):
        SessionMixin.settings = self.settings
        RedisMixin.settings = self.settings
        super().initialize()

    def get(self):
        self.post()

    def post(self):
        self.forbidden()

    def forbidden(self):
        self.set_status(403, 'Forbidden')
        ret_data = dict(success=False, code=403, message='禁止访问', showType=9, data='')
        self.write_json(data=ret_data)

    # 返回json格式字符串
    def write_json(self, data:dict):
        if isinstance(data, dict): data = json.dumps(data, ensure_ascii=False)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(data)

    # 返回xml格式字符串
    def write_xml(self, data:str):
        self.set_header("Content-Type", "text/xml; charset=UTF-8")
        self.finish(data)

    # 获取json格式请求参数
    def get_json_arguments(self):
        params = self.request.body
        if isinstance(params, bytes): params = params.decode('utf8')
        try:
            params = json.loads(params)
            params = isinstance(params, dict) and munchify(params) or {}
        except Exception as e:
            app_log.error(e)
            params = {}
        return params

    # 获取xml格式请求参数
    def get_xml_arguments(self):
        params = self.request.body
        if isinstance(params, bytes): params = params.decode('utf8')
        try:
            params = ET.fromstring(params)
        except Exception as e:
            app_log.error(e)
            params = None
        return params

    # 获取当前用户信息
    def get_current_user_async(self):
        return self.current_user


class BaseDBModel(SessionMixin):
    def __init__(self, db_sess:SQLAlchemy=None):
        if db_sess is not None: self.settings['db'] = db_sess

class BaseRedisModel(RedisMixin):
    def __init__(self, redis_sess:Redis=None):
        if redis_sess is not None: self.settings['redis'] = redis_sess

    """
    取值(字符串)
    """
    async def get(self, name):
        with self.redis_session() as redis:
            try:
                value = await as_future(redis.get(name=name))
                value = value.decode('utf8') if isinstance(value, bytes) else value
                if value: value = json.loads(value)
            except Exception as e:
                app_log.error(e)
                value = None
            finally:
                return value

    """
    设值(字符串)
    """
    async def set(self, name, value, ex=None, px=None, nx=False, xx=False):
        with self.redis_session() as redis:
            try:
                value and (await as_future(redis.set(name=name, value=json.dumps(value, ensure_ascii=False), ex=ex, px=px, nx=nx, xx=xx)))
            except Exception as e:
                app_log.error(e)

    """
    删值
    """
    async def delete(self, names):
        with self.redis_session() as redis:
            try:
                await as_future(redis.delete(names))
            except Exception as e:
                app_log.error(e)

    """
    取值(键值对)
    """
    async def hgetall(self, name):
        with self.redis_session() as redis:
            try:
                data = dict()
                values = await as_future(redis.hgetall(name))
                for key, value in values.items():
                    value = value.decode('utf8') if isinstance(value, bytes) else value
                    if value: data[key] = json.loads(value)
            except Exception as e:
                app_log.error(e)
                data = dict()
            finally:
                return data

    """
    设值(键值对)
    """
    async def hset(self, name, key, value, ex=None):
        with self.redis_session() as redis:
            try:
                value = json.dumps(value, ensure_ascii=False)
                value and (await as_future(redis.hset(name, key, value)))
                ex and (await as_future(redis.expire(name, ex)))
            except Exception as e:
                app_log.error(e)

    """
    批量设值(键值对)
    """
    async def hmset(self, name, data, ex=None):
        with self.redis_session() as redis:
            try:
                for key, value in data.items():
                    data[key] = json.dumps(value, ensure_ascii=False)
                data and (await as_future(redis.hmset(name, data)))
                ex and (await as_future(redis.expire(name, ex)))
            except Exception as e:
                app_log.error(e)

    """
    取一个值(键值对)
    """
    async def hget(self, name, key):
        with self.redis_session() as redis:
            try:
                data = await as_future(redis.hget(name, key))
                data = data.decode('utf8') if isinstance(data, bytes) else data
                if data: data = json.loads(data)
            except Exception as e:
                data = None
                app_log.error(e)
            finally:
                return data

    """
    删一个值(键值对)
    """
    async def hdel(self, name, key):
        with self.redis_session() as redis:
            try:
                await as_future(redis.hdel(name, key))
            except Exception as e:
                app_log.error(e)

    """
    设值(列表)
    """
    async def lpush(self, name, value, ex=None):
        with self.redis_session() as redis:
            try:
                if not isinstance(value, list): value = [value]
                if value:
                    for v in value:
                        await as_future(redis.lpush(name, json.dumps(v, ensure_ascii=False)))
                ex and (await as_future(redis.expire(name, ex)))
            except Exception as e:
                app_log.error(e)

    """
    取值(列表)
    """
    async def lgetall(self, name):
        with self.redis_session() as redis:
            try:
                end = (await as_future(redis.llen(name)))
                data = (await as_future(redis.lrange(name, 0, end)))
                for v in data:
                    if v: v = json.loads(v)
            except Exception as e:
                app_log.error(e)
                data = []
            finally:
                return data

    """
    清空并设值(列表)
    """
    async def lnpush(self, name, value, ex=None):
        with self.redis_session() as redis:
            try:
                await as_future(redis.delete(name))
                await self.lpush(name=name, value=value, ex=ex)
            except Exception as e:
                app_log.error(e)
