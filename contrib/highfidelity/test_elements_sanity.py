# Unfamiliar with the ELements RPC interface?
# See: https://github.com/ElementsProject/elementsbp-api-reference/blob/master/api.md  # noqa: E501

from gevent import monkey; monkey.patch_all()  # noqa: E702

import logging
import time

import gevent
import pytest

from .alice_and_bob import alice_and_bob
from .kill_elementsd_before_each_function import *  # noqa: F401, F403
from .kill_elementsd_before_each_function import kill_all_elementsd
from .test_framework.authproxy import JSONRPCException
from .blockchain import Elements
from .wallet import Wallet, DEFAULT_FEE, SEED_AMOUNT


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('test_elements_wallet')


def generate_signing_key(node):
    address = node.rpc('getnewaddress')
    result = node.rpc('validateaddress', address)
    assert result['isvalid']


# NOTE: We had concerns about unpredictable startup behavior of
# elementds. Hence the variety of "immediate" and "delayed" tests.


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
    N_RUNS = 3
    exceptions = list()
    passed = list()
    for n in range(N_RUNS):
        logging.info(f'=== {n+1} of {N_RUNS}: test_immediate_generate_blocks')
        kill_all_elementsd()
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
        logger.info(f'giving {node_name} 5 seconds to warm up...')
        time.sleep(5)
        for _ in range(100):
            generate_signing_key(node)


def test_delayed_generate_blocks():
    N_RUNS = 3
    exceptions = list()
    passed = list()
    for n in range(N_RUNS):
        logging.info(f'=== {n+1} of {N_RUNS}: test_immediate_generate_blocks')
        kill_all_elementsd()
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
def test_async_generate_blocks():
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
            result = node.generate_block()
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


def test_roundtrips():
    with alice_and_bob() as (alice, bob):
        AMOUNT = 10
        ROUNDTRIPS = 10
        for _ in range(ROUNDTRIPS):
            alice_balance = alice.balance
            bob_balance = bob.balance
            Wallet.transact(alice, bob, AMOUNT)
            assert alice_balance - AMOUNT - DEFAULT_FEE == alice.balance
            assert bob_balance + AMOUNT == bob.balance
            Wallet.transact(bob, alice, AMOUNT)
            assert alice_balance - DEFAULT_FEE == alice.balance
            assert bob_balance - DEFAULT_FEE == bob.balance
        assert SEED_AMOUNT - DEFAULT_FEE * ROUNDTRIPS == alice.balance
        assert SEED_AMOUNT - DEFAULT_FEE * ROUNDTRIPS == bob.balance


def test_roundtrips_and_generate_blocks():
    with alice_and_bob() as (alice, bob):
        AMOUNT = 10
        ROUNDTRIPS = 100
        ROUNDTRIPS_PER_BLOCK = 10
        for n in range(ROUNDTRIPS):
            alice_balance = alice.balance
            bob_balance = bob.balance
            Wallet.transact(alice, bob, AMOUNT)
            assert alice_balance - AMOUNT - DEFAULT_FEE == alice.balance
            assert bob_balance + AMOUNT == bob.balance
            Wallet.transact(bob, alice, AMOUNT)
            assert alice_balance - DEFAULT_FEE == alice.balance
            assert bob_balance - DEFAULT_FEE == bob.balance
            if 0 == (n + 1) % ROUNDTRIPS_PER_BLOCK:
                assert None is Wallet.master_node.generate_block()
        assert SEED_AMOUNT - DEFAULT_FEE * ROUNDTRIPS == alice.balance
        assert SEED_AMOUNT - DEFAULT_FEE * ROUNDTRIPS == bob.balance
