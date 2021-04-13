import time

import pytest
from phoenixdb.errors import NotSupportedError

from curd import Session
from tests.conf import hbase_conf
from tests.operations import (
    delete, normal_filter, filter_with_order_by, thread_pool, update,
    create_many)


def create_test_table(session):
    session.execute('CREATE SCHEMA IF NOT EXISTS CURD')
    session.execute('DROP TABLE IF EXISTS CURD.TEST')
    session.execute(
        """CREATE TABLE IF NOT EXISTS CURD.TEST ("id" bigint NOT NULL, "text" varchar, CONSTRAINT pk PRIMARY KEY ("id")) DATA_BLOCK_ENCODING='FAST_DIFF', COMPRESSION = 'GZ'""")
    return 'CURD.TEST'


def create(session, create_test_table):
    collection = create_test_table(session)

    data = {'id': 100, 'text': 'test'}

    session.create(collection, data)
    # do test for habse
    # with pytest.raises(DuplicateKeyError):
    #     session.create(collection, data, mode='insert')

    assert data == session.get(collection, [('=', 'id', 100)])

    time.sleep(10)
    data2 = {'id': 100, 'text': 't2'}
    session.create(collection, data2, mode='replace')

    assert data != session.get(collection, [('=', 'id', 100)])


def update(session, create_test_table):
    collection = create_test_table(session)
    data = {'id': 100, 'text': 'test'}
    session.create(collection, data)
    with pytest.raises(NotSupportedError):
        session.update(collection, {'text': 't2'}, [('=', 'id', data['id'])])


def test_hbase():
    session = Session([hbase_conf])
    print('>>>>>>>>>>>>>> test create <<<<<<<<<<<<<<<<<')
    create(session, create_test_table)

    print('>>>>>>>>>>>>>> test create <<<<<<<<<<<<<<<<<')
    create_many(Session([hbase_conf]), create_test_table, True)

    print('>>>>>>>>>>>>>> test update <<<<<<<<<<<<<<<<<')
    update(session, create_test_table)

    print('>>>>>>>>>>>>>> test delete <<<<<<<<<<<<<<<<<')
    delete(session, create_test_table)

    print('>>>>>>>>>>>>>> test normal filter <<<<<<<<<<<<<<<<<')
    normal_filter(session, create_test_table, size=50)

    print('>>>>>>>>>>>>>> test order by filter <<<<<<<<<<<<<<<<<')
    filter_with_order_by(session, create_test_table, size=50)

    print('>>>>>>>>>>>>>> test multi thread create <<<<<<<<<<<<<<<<<')
    thread_pool(session, create_test_table, size=100)
