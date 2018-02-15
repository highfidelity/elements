from gevent import monkey; monkey.patch_all()  # noqa: E702

import logging
import subprocess
import time

import gevent
import pytest

from .test_framework.authproxy import JSONRPCException
from .blockchain import Elements


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('test_elements_wallet')


def kill_all_elementd():
    result = subprocess.run(['pkill', 'elementsd'])
    if 0 == result.returncode:
        logging.info('killed preexisting elementsd')
        logging.info(f'pause after killing elementsd...')
        time.sleep(5)
    elif 1 == result.returncode:
        # No processes were matched. OK.
        pass
    else:
        msg = f'pkill failed with {result.returncode}; see `man pkill`'
        raise AssertionError(msg)


def setup_function(function):
    kill_all_elementd()


def generate_signing_key(node):
    address = node.rpc('getnewaddress')
    result = node.rpc('validateaddress', address)
    assert result['isvalid']


def test_immediate_generate_signing_keys():
    # Fire up a daemon and associated proxy, returning the `node` as
    # quickly as possible so that we can start hammering it right away.
    # We accept initial rpc errors since the daemon may not yet be up.
    # Once the daemon is up then we do not accept further rpc errors.
    # Finally, we ensure that the daemon is up by the end of the test.
    node_name = 'test_elements_wallet'
    with Elements.node(node_name, _ensure_signing_key=False) as node:
        is_daemon_up = False
        for _ in range(100):
            try:
                generate_signing_key(node)
                is_daemon_up = True
            except (ConnectionRefusedError, JSONRPCException):
                if is_daemon_up:
                    raise
        assert is_daemon_up


def test_immediate_generate_blocks():
    N_RUNS = 10
    exceptions = list()
    passed = list()
    for n in range(N_RUNS):
        logging.info(f'=== {n+1} of {N_RUNS}: test_immediate_generate_blocks')
        kill_all_elementd()
        try:
            with Elements.node('master'):
                logging.info(f'=== test {n+1} of {N_RUNS} passed')
                passed.append(n)
        except (ConnectionRefusedError, JSONRPCException) as e:
            logging.error(f'=== test {n+1} of {N_RUNS} failed: {e}')
            exceptions.append((n, e))
    logging.info(f'passed {len(passed)} of {N_RUNS}: {passed}')
    logging.error(f'exceptions: {exceptions}')
    assert not exceptions


def test_delayed_generate_signing_keys():
    # Since we give the daemon ample time to warm up we expect no
    # errors.
    node_name = 'test_elements_wallet'
    with Elements.node(node_name, _ensure_signing_key=False) as node:
        logger.info(f'giving {node_name} 10 seconds to warm up...')
        time.sleep(10)
        for _ in range(100):
            generate_signing_key(node)


def test_delayed_generate_blocks():
    N_RUNS = 10
    exceptions = list()
    passed = list()
    for n in range(N_RUNS):
        logging.info(f'=== {n+1} of {N_RUNS}: test_immediate_generate_blocks')
        kill_all_elementd()
        try:
            # _warm_up_master=True means: Start the master daemon then
            # before issuing any commands to it sleep for awhile.
            with Elements.node('master', _warm_up_master=True):
                logging.info(f'=== test {n+1} of {N_RUNS} passed')
                passed.append(n)
        except (ConnectionRefusedError, JSONRPCException) as e:
            logging.error(f'=== test {n+1} of {N_RUNS} failed: {e}')
            exceptions.append((n, e))
    logging.info(f'passed {len(passed)} of {N_RUNS}: {passed}')
    logging.error(f'exceptions: {exceptions}')
    assert not exceptions


@pytest.mark.xfail
def test_async_delayed_generate_blocks():
    # Create a master daemon. Fire up an increasing number of asynchronous
    # clients that attempt to create blocks at the master daemon. When
    # a client fails with an unexpected result the test is failed.
    class ConcurrencyException(Exception):
        pass

    class UnexpectedResult(Exception):
        pass

    def create_block():
        node = Elements.Node('master')
        try:
            result = Elements._generate_block(node)
        except JSONRPCException as e:
            if 'already have block' != e.error['message']:
                raise
        else:
            EXPECTED_RESULTS = (None, 'duplicate', 'duplicate-inconclusive')
            if result not in EXPECTED_RESULTS:
                raise UnexpectedResult(result)

    # Create a master daemon with an initial blockchain...
    with Elements.node('master'):
        # ... and with ever increasing concurrency ...
        for concurrency in range(100):
            # ... fire up asynchronous clients that attempt to generate
            # blocks at the master daemon.
            greenlets = [
                gevent.spawn(create_block) for _ in range(concurrency)]
            gevent.joinall(greenlets)
            # If any client raised an Exception the test is over.
            if not all(None is greenlet.exception for greenlet in greenlets):
                # Report the extent to which the test succeeded and the
                # exceptions that caused it to fail.
                logger.critical(
                    f'async jobs failed with concurrency {concurrency}')
                for greenlet in greenlets:
                    if None is not greenlet.exception:
                        logger.critical(str(greenlet.exception))
                assert False
