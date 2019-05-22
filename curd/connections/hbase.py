import copy
import random
import phoenixdb
from ..errors import (
    UnexpectedError, OperationFailure, ProgrammingError,
    ConnectError,
    DuplicateKeyError
)
from .utils.sql import (
    query_parameters_from_create,
    query_parameters_from_update,
    query_parameters_from_delete,
    query_parameters_from_filter
)
from . import (
    BaseConnection, DEFAULT_FILTER_LIMIT, DEFAULT_TIMEOUT, OP_RETRY_WARNING,
    CURD_FUNCTIONS
)
from .mysql import MysqlConnection, MysqlConnectionPool


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
        if not self.cursor:
            self.connect(self._conf)

        self.conn._read_timeout = timeout
        self.conn._write_timeout = timeout

        try:
            self.cursor.execute(query, params)
        except phoenixdb.errors.ProgrammingError as e:
            raise ProgrammingError(origin_error=e)
        except Exception as e:
            if isinstance(e.args, tuple) and len(e.args) >= 1:
                if e.args[0] in self.pe_mysql_error_code_list:
                    raise ProgrammingError(origin_error=e)
                elif e.args[0] in self.of_mysql_error_code_list:
                    raise OperationFailure(origin_error=e)
                else:
                    raise UnexpectedError(origin_error=e)
            else:
                raise UnexpectedError(origin_error=e)
        else:
            if not self.cursor._frame:
                return []
            return list(self.cursor.fetchall())

    def create(self, collection, data, mode='INSERT', compress_fields=None, **kwargs):
        query, params = query_parameters_from_create(
            collection, data, mode.upper(), compress_fields
        )
        query = self.adapt_standard_query(query)
        try:
            self.execute(query, params, **kwargs)
        except ProgrammingError as e:
            if e._origin_error.args[0] == self.pe_duplicate_entry_key_error_code:
                raise DuplicateKeyError(str(e._origin_error))
            else:
                raise

    def create_many(self, collection, data, mode='INSERT', compress_fields=None, **kwargs):
        raise NotImplementedError('not supported')

    def update(self, collection, data, filters, **kwargs):
        raise phoenixdb.errors.NotSupportedError(
            'hbase do not support update, use create with insert/replace mode instead')

    def delete(self, collection, filters, **kwargs):
        filters = self._check_filters(filters)
        query, params = query_parameters_from_delete(collection, filters)
        query = self.adapt_standard_query(query)
        self.execute(query, params, **kwargs)

    def filter(self, collection, filters=None, fields=None,
               order_by=None, limit=DEFAULT_FILTER_LIMIT, **kwargs):
        filters = self._check_filters(filters)
        query, params = query_parameters_from_filter(
            collection, filters, fields, order_by, limit)
        query = self.adapt_standard_query(query)
        rows = self.execute(query, params, **kwargs)
        return rows

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
