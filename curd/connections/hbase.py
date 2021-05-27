import copy
import random

import phoenixdb

from . import (
    DEFAULT_TIMEOUT
)
from . import logger
from .mysql import MysqlConnection, MysqlConnectionPool
from ..errors import (
    UnexpectedError, OperationFailure, ProgrammingError
)


class HbaseConnection(MysqlConnection):

    def __init__(self, conf):
        MysqlConnection.__init__(self, conf)

    def _connect(self, conf):
        conf = copy.deepcopy(conf)

        self.max_op_fail_retry = conf.pop('max_op_fail_retry', 0)
        self.default_timeout = conf.pop('timeout', DEFAULT_TIMEOUT)

        conn = phoenixdb.connect(random.choice(conf['urls']), autocommit=True)
        cursor = conn.cursor(cursor_factory=phoenixdb.cursor.DictCursor)
        return conn, cursor

    def _execute(self, query, params, timeout, cursor_func='execute'):
        # 直接写的upsert，为保证成功，重建连接
        is_raw_upsert = query.upper().strip().startswith('UPSERT') and params is None  # 直接用sql的插入更新
        if is_raw_upsert:
            logger.warning('force close connection and cursor for UPSERT STATEMENT, should use create func instead')
            self.close()

        if not self.cursor:
            self.connect(self._conf)

        self.conn._read_timeout = timeout
        self.conn._write_timeout = timeout

        try:
            func = getattr(self.cursor, cursor_func)
            func(query, params)
        except phoenixdb.errors.ProgrammingError as e:
            raise ProgrammingError(origin_error=e)
        except Exception as e:
            errs = phoenixdb.errors
            if any(map(lambda x: isinstance(e, x), [errs.InternalError, errs.OperationalError, BrokenPipeError])):
                raise OperationFailure(origin_error=e)  # will retry
            else:
                raise UnexpectedError(origin_error=e)
        else:
            try:
                should_have_return = query.upper().strip().startswith('SELECT')

                # 1. 确实有返回的
                # 2. http连接服务端timeout时，有时execute select语句不会抛异常，frame也不是None, 而是在fetch时抛，
                # 此时需要新建conn并重试，因此抛OperationFailure.
                # 3. upsert的问题已在本函数头通过暴力重连解决. upsert时正常结束和失败结果frame都是None
                # TODO 此处办法只是规避，要解决根本问题得弄清为何avatica服务端已经timeout还会返回http 200
                if self.cursor._frame is not None or should_have_return:  # 有返回的语句, 返回结果是空，frame也不应是None
                    return list(self.cursor.fetchall())
            except phoenixdb.errors.ProgrammingError as e:
                raise OperationFailure(origin_error=e)

    def update(self, collection, data, filters, **kwargs):
        raise phoenixdb.errors.NotSupportedError(
            'hbase do not support update, use create with insert/replace mode instead')

    @staticmethod
    def adapt_standard_query(query):
        """ phoenix sql do not support all standards, hack for quick implement
            1. '`' quote not support
            2. UPSERT instead of INSERT
            3. UPSERT instead of INSERT IGNORE
            4. UPSERT instead of REPLACE
            5. '?' instead of '%s'
        """
        new_query = query.replace('`', '"').replace('%s', '?') \
            .replace('REPLACE INTO', 'UPSERT INTO').replace('INSERT INTO', 'UPSERT INTO')
        if 'INSERT IGNORE INTO' in new_query:
            new_query = new_query.replace('INSERT IGNORE INTO', 'UPSERT INTO') + ' ON DUPLICATE KEY IGNORE'
        return new_query


class HbaseConnectionPool(MysqlConnectionPool):
    def __init__(self, *args, **kwargs):
        MysqlConnectionPool.__init__(self, *args, **kwargs)

    def get_connection(self):
        return HbaseConnection(*self._args, **self._kwargs)
