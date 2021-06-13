import json
from contextlib import contextmanager
from typing import Iterator, Optional
from tornado_models import MissingDatabaseSettingError, MissingFactoryError
from tornado_models import as_future
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from tornado.log import app_log
from sqlalchemy.orm.state import InstanceState
from decimal import Decimal
from datetime import datetime
from munch import munchify


class SessionMixin:
    _session = None  # type: Optional[Session]
    settings = {}

    @contextmanager
    def db_session(self) -> Iterator[Session]:
        session = None

        try:
            session = self._make_session()

            yield session
        except Exception:
            if session:
                session.rollback()
            raise
        else:
            session.commit()
        finally:
            if session:
                session.close()

    def on_finish(self):
        next_on_finish = None

        try:
            next_on_finish = super(SessionMixin, self).on_finish
        except AttributeError:
            pass

        if self._session:
            self._session.commit()
            self._session.close()

        if next_on_finish:
            next_on_finish()

    @property
    def db_conn(self) -> Session:
        if not self._session:
            self._session = self._make_session()
        return self._session

    def _make_session(self) -> Session:
        if not self.settings:
            raise MissingFactoryError()
        db = self.settings.get('db')
        if not db:
            raise MissingDatabaseSettingError()
        return db.sessionmaker()


class SessionEx(Session):
    """The SessionEx extends the default session system with bind selection.
    """

    def __init__(self, db, autocommit=False, autoflush=True, **options):
        self.db = db
        bind = options.pop('bind', None) or db.engine
        binds = options.pop('binds', db.get_binds())

        super().__init__(
            autocommit=autocommit,
            autoflush=autoflush,
            bind=bind,
            binds=binds,
            **options
        )

    def get_bind(self, mapper=None, clause=None):
        """Return the engine or connection for a given model or
        table, using the `__bind_key__` if it is set.
        """

        if mapper is not None:
            try:
                # SA >= 1.3
                persist_selectable = mapper.persist_selectable
            except AttributeError:
                # SA < 1.3
                persist_selectable = mapper.mapped_table

            info = getattr(persist_selectable, 'info', {})
            bind_key = info.get('bind_key')

            if bind_key is not None:
                return self.db.get_engine(bind=bind_key)

        return super().get_bind(mapper, clause)


class BindMeta(DeclarativeMeta):
    def __init__(cls, name, bases, d):
        bind_key = d.pop('__bind_key__', None) or getattr(
            cls, '__bind_key__', None
        )

        super(BindMeta, cls).__init__(name, bases, d)

        if (
            bind_key is not None
            and getattr(cls, '__table__', None) is not None
        ):
            cls.__table__.info['bind_key'] = bind_key


def to_dict(self):
    rows = dict()
    for k, v in self.__dict__.items():
        if isinstance(v, InstanceState):
            continue
        elif isinstance(v, datetime):
            v = v.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(v, Decimal):
            v = str(v.quantize(Decimal('0.00')))
        elif hasattr(v, '__tablename__'):
            v = v.to_dict()
        elif isinstance(v, list):
            y = []
            for x in v:
                if hasattr(x, '__tablename__'):
                    y.append(x.to_dict())
                else:
                    y.append(x)
            v = y        
        rows[k] = v
    return rows

def to_json(self):
    return json.dumps(self.to_dict(), ensure_ascii=False)

def to_object(self):
    return munchify(self.to_dict())

@classmethod
async def query_one_by_filter(cls, *filter):
    try:
        res = await as_future(
            cls.db.query(cls).filter(*filter).first()
        )
    except Exception:
        res = False
        raise
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res
    

@classmethod
async def query_all(cls):
    try:
        res = await as_future(
            cls.db.query(cls).order_by(cls.id.desc()).all()
        )
    except Exception:
        res = False
        raise
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res
    

@classmethod
async def query_by_page(cls, page:int=1, per_page:int=10):
    try:
        res = await as_future(
            cls.db.query(cls).order_by(cls.id.desc()).paginate(page, per_page)
        )
    except Exception:
        res = False
        raise
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res
    

@classmethod
async def query_by_filter(cls, *filter):
    try:
        res = await as_future(
            cls.db.query(cls).filter(*filter).order_by(cls.id.desc()).all()
        )
    except Exception:
        res = False
        raise
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res
    

@classmethod
async def query_by_filter_and_page(cls, *filter, page:int=1, per_page:int=10):
    try:
        res = await as_future(
            cls.db.query(cls).filter(*filter).order_by(cls.id.desc()).paginate(page, per_page)
        )
    except Exception:
        res = False
        raise
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res

@classmethod
async def update_by_filter(cls, *filter, data:dict):
    try:
        res = await as_future(
            cls.db.query(cls).filter(*filter).with_for_update().update(data, synchronize_session=False)
        )
    except Exception:
        if cls.db:
            await as_future(cls.db.rollback())
        res = False
        raise
    else:
        await as_future(cls.db.commit())
        await as_future(cls.db.flush())
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res
    

@classmethod
async def delete_by_filter(cls, *filter):
    try:
        res = await as_future(
            cls.db.query(cls).filter(*filter).delete(synchronize_session=False)
        )
    except Exception:
        if cls.db:
            await as_future(cls.db.rollback())
        res = False
        raise
    else:
        await as_future(cls.db.commit())
        await as_future(cls.db.flush())
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res

@classmethod
async def add_all_data(cls, data:list):
    try:
        await as_future(
            cls.db.add_all(data)
        )
    except Exception:
        if cls.db:
            await as_future(cls.db.rollback())
        res = False
        raise
    else:
        await as_future(cls.db.commit())
        await as_future(cls.db.flush())
        res = True
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res

@classmethod
async def add_one_data(cls, data:DeclarativeMeta):
    try:
        await as_future(
            cls.db.add(data)
        )
    except Exception:
        if cls.db:
            await as_future(cls.db.rollback())
        res = False
        raise
    else:
        await as_future(cls.db.commit())
        await as_future(cls.db.flush())
        res = True
    finally:
        if cls.db:
            await as_future(cls.db.close())
        return res


class SQLAlchemy:
    def __init__(
        self, url=None, binds=None, session_options=None, engine_options=None
    ):
        self.Model = self.make_declarative_base()
        self.Model.to_dict = to_dict
        self.Model.to_json = to_json
        self.Model.to_object = to_object
        self.Model.query_one_by_filter = query_one_by_filter
        self.Model.query_all = query_all
        self.Model.query_by_page = query_by_page
        self.Model.query_by_filter = query_by_filter
        self.Model.query_by_filter_and_page = query_by_filter_and_page
        self.Model.update_by_filter = update_by_filter
        self.Model.delete_by_filter = delete_by_filter
        self.Model.add_all_data = add_all_data
        self.Model.add_one_data = add_one_data
        self._engines = {}

        self.configure(
            url=url,
            binds=binds,
            session_options=session_options,
            engine_options=engine_options,
        )

    def configure(
        self, url=None, binds=None, session_options=None, engine_options=None
    ):
        self.url = url
        self.binds = binds or {}
        self._engine_options = engine_options or {}

        self.sessionmaker = sessionmaker(
            class_=SessionEx, db=self, **(session_options or {})
        )
        self.Model.db = self.sessionmaker()

    @property
    def engine(self):
        return self.get_engine()

    @property
    def metadata(self):
        return self.Model.metadata

    def create_engine(self, bind=None):
        if not self.url and not self.binds:
            raise MissingDatabaseSettingError()

        if bind is None:
            url = self.url
        else:
            if bind not in self.binds:
                raise RuntimeError('bind {} undefined.'.format(bind))
            url = self.binds[bind]

        return create_engine(url, **self._engine_options)

    def get_engine(self, bind=None):
        """Returns a specific engine. cached in self._engines """
        engine = self._engines.get(bind)

        if engine is None:
            engine = self.create_engine(bind)
            self._engines[bind] = engine

        return engine

    def get_tables_for_bind(self, bind=None):
        """Returns a list of all tables relevant for a bind."""
        return [
            table
            for table in self.Model.metadata.tables.values()
            if table.info.get('bind_key') == bind
        ]

    def get_binds(self):
        """Returns a dictionary with a table->engine mapping.
        This is suitable for use of sessionmaker(binds=db.get_binds()).
        """
        binds = [None] + list(self.binds)

        result = {}

        for bind in binds:
            engine = self.get_engine(bind)
            tables = self.get_tables_for_bind(bind)

            result.update(dict((table, engine) for table in tables))

        return result

    def _execute_for_all_tables(self, bind, operation, skip_tables=False):
        if bind == '__all__':
            binds = [None] + list(self.binds)
        elif isinstance(bind, str) or bind is None:
            binds = [bind]
        else:
            binds = bind

        for bind in binds:
            extra = {}

            if not skip_tables:
                tables = self.get_tables_for_bind(bind)
                extra['tables'] = tables

            op = getattr(self.Model.metadata, operation)
            op(bind=self.get_engine(bind), **extra)

    def create_all(self, bind='__all__'):
        """Creates all tables.
        """
        self._execute_for_all_tables(bind, 'create_all')

    def drop_all(self, bind='__all__'):
        """Drops all tables.
        """
        self._execute_for_all_tables(bind, 'drop_all')

    def make_declarative_base(self):
        return declarative_base(metaclass=BindMeta)