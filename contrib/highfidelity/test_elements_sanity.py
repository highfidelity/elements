# Unfamiliar with the ELements RPC interface?
# See: https://github.com/ElementsProject/elementsbp-api-reference/blob/master/api.md#createrawtransaction  # noqa: E501

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
        time.sleep(2)
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
    N_RUNS = 3
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


def test_generate_transactions():
    # MONEY_ASSET_ID = 'bitcoin'
    DEFAULT_FEE = 1
    MAX_CONFIRMATIONS = 9999999  # This is the default used by the daemons.
    MIN_CONFIRMATIONS = 0  # Accept unconfirmed transactions during testing.
    SEED_AMOUNT = 1000

    class Wallet:
        master_node = None

        def __init__(self, node):
            # We do not have an implementation of a lightweight wallet
            # for generating and storing keys and signing transactions.
            # As a quick hack in testing we use a full node for this
            # purpose. And since our tests monitor transaction activity
            # at the master node, we register all wallet-related
            # addresses as watch-only address at the master node.
            self._node = node
            self._initialize_address()
            self._expected_balance = 0

        @property
        def balance(self):
            """Validate and return the wallet's balance."""
            result = sum(x['amount'] for x in self._unspent(self.address))
            assert self._expected_balance == result
            return result

        @classmethod
        def transact(
            cls,
            sender,
            receiver,
            amount,
            output_asset_ids={},
            details=[]
        ):
            if sender:
                result = cls._transact(
                    sender, receiver, amount, output_asset_ids, details)
                sender._expected_balance -= amount + DEFAULT_FEE
                receiver._expected_balance += amount
            else:
                result = cls._airdrop(receiver, amount)
                receiver._expected_balance += amount
            return result

        def seed(self, amount):
            self.transact(None, self, amount)

        def sign(self, raw_transaction, details=None):
            return self._node.rpc(
                'signrawtransaction', raw_transaction, details)['hex']

        # def certify(self, item_id):
        #     assert 'item_id' not in self.certificates
        #     self.certificates[item_id] = self._unconfidential_address()
        #     self._master_node.importaddress(self.certificates[item_id])

        @classmethod
        def _script_pub_key(cls, input_):
            t = cls.master_node.rpc('getrawtransaction', input_['txid'], True)
            return t['vout'][input_['vout']]['scriptPubKey']['hex']

        @classmethod
        def _unspent_details(cls, inputs):
            result = list()
            for input_ in inputs:
                result.append({
                    'txid': input_['txid'],
                    'vout': input_['vout'],
                    'scriptPubKey': cls._script_pub_key(input_)
                })
            return result

        @classmethod
        def _transact(
            cls, sender, receiver, amount, output_asset_ids, details
        ):
            inputs = cls._unspent(sender.address)
            outputs = {
                receiver.address: amount,
                'fee': DEFAULT_FEE,
                sender.address: sender.balance - DEFAULT_FEE - amount
            }
            txn_raw = cls._raw_transaction(inputs, outputs, output_asset_ids)
            details = details or cls._unspent_details(inputs)
            txn_signed = sender.sign(txn_raw, details)
            return cls.master_node.rpc('sendrawtransaction', txn_signed, True, True)  # noqa: E501

        @classmethod
        def _airdrop(cls, receiver, amount):
            inputs = []
            outputs = {receiver.address: amount}
            txn_raw = cls._raw_transaction(inputs, outputs)
            txn_funded = cls.master_node.rpc(
                'fundrawtransaction', txn_raw)['hex']
            txn_signed = cls.master_node.rpc(
                'signrawtransaction', txn_funded)['hex']
            return cls.master_node.rpc(
                'sendrawtransaction', txn_signed, True, True)

        @classmethod
        def _raw_transaction(cls, inputs, outputs, output_asset_ids={}):
            return cls.master_node.rpc(
                'createrawtransaction',
                inputs,
                outputs,
                1,  # Why 1? Why not 0?
                output_asset_ids)

        @classmethod
        def _unspent(cls, address):
            return cls.master_node.rpc(
                'listunspent',
                MIN_CONFIRMATIONS,
                MAX_CONFIRMATIONS,
                [address])

        def _initialize_address(self):
            self.address = self._unconfidential_address()
            self.master_node.rpc('importaddress', self.address)

        def _unconfidential_address(self):
            address_new = self._node.rpc('getnewaddress')
            address_validated = \
                self._node.rpc('validateaddress', address_new)
            return address_validated['unconfidential']

    def run(test_function):
        with Elements.node('master') as master_node:
            Wallet.master_node = master_node
            with Elements.node('alice') as node_alice:
                alice = Wallet(node_alice)
                alice.seed(SEED_AMOUNT)
                with Elements.node('bob') as node_bob:
                    bob = Wallet(node_bob)
                    bob.seed(SEED_AMOUNT)
                    test_function(alice, bob)

    def _test_function_roundtrips(alice, bob):
        ROUNDTRIPS = 10
        AMOUNT = 10
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

    run(_test_function_roundtrips)

