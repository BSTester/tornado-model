from sqlalchemy.ext.declarative import DeclarativeMeta
from tornado.web import RequestHandler
from tornado.log import app_log
from tornado_model.sqlalchemy import SessionMixin
from tornado_model.redis import RedisMixin
from xml.etree import cElementTree as ET
from sqlalchemy.orm.state import InstanceState
from decimal import Decimal
from datetime import datetime
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
            self.set_status(401, '登录超时')
            self.write_json(dict(code=401, status='FAIL', message='登录超时, 请重新登录', data=''))
        elif self.current_user is False:
            self.set_status(403, '禁止访问')
            self.write_json(dict(code=403, status='FAIL', message='Forbidden', data=''))
        else:
            await f(self, *args, **kwargs)
    return wrapper


class BaseRequestHandler(RedisMixin, SessionMixin, RequestHandler):
    def get(self):
        self.post()

    def post(self):
        self.forbidden()

    def forbidden(self):
        self.set_status(403, '禁止访问')
        ret_data = dict(code=403, status='FAIL', message='Forbidden', data='')
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
            params = json.loads(params, encoding='utf8')
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
        pass



class BaseModel(DeclarativeMeta):
    __table_args__ = {
        'mysql_engine':'InnoDB',
        'mysql_charset':'utf8mb4',
        'mysql_row_format':'dynamic'
        }

    def to_dict(self):
        rows = dict()
        for k, v in self.__dict__.items():
            if isinstance(v, InstanceState):
                continue
            elif isinstance(v, datetime):
                v = v.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(v, Decimal):
                v = str(v.quantize(Decimal('0.00')))
            elif isinstance(v, DeclarativeMeta):
                v = v.to_dict()
            rows[k] = v
        return rows

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)