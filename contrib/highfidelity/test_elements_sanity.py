# Unfamiliar with the ELements RPC interface?
# See: https://github.com/ElementsProject/elementsbp-api-reference/blob/master/api.md  # noqa: E501

from gevent import monkey; monkey.patch_all()  # noqa: E702

import contextlib
import logging
import time

import gevent
import pytest

from .kill_elementsd_before_each_function import *  # noqa: F403
from .test_framework.authproxy import JSONRPCException
from .blockchain import Elements


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
        result = sum(
            x['amount'] for x in self._all_utxo(self.address))
        assert self._expected_balance == result
        return result

    @classmethod
    def transact(
        cls,
        sender,
        receiver,
        amount,
        output_asset_ids={},
        utxo_details=[]
    ):
        # utxo_details are unspent transaction ot
        if sender:
            result = cls._transact(
                sender, receiver, amount, output_asset_ids, utxo_details)
            sender._expected_balance -= amount + DEFAULT_FEE
            receiver._expected_balance += amount
        else:
            result = cls._airdrop(receiver, amount)
            receiver._expected_balance += amount
        return result

    def seed(self, amount):
        self.transact(None, self, amount)

    def sign(self, raw_transaction, utxo_details=None):
        """Sign a raw transaction

        Arguments:
            raw_transaction (hex): the transaction to sign as a
                serialized transaction
            utxo_details (list; optional): The previous outputs being
                spent by this transaction

        For more information on utxo_details, see:
            https://bitcoin.org/en/developer-reference#signrawtransaction

        """
        return self._node.rpc(
            'signrawtransaction', raw_transaction, utxo_details)['hex']

    # def certify(self, item_id):
    #     assert 'item_id' not in self.certificates
    #     self.certificates[item_id] = self._unconfidential_address()
    #     self._master_node.importaddress(self.certificates[item_id])

    @classmethod
    def _script_pub_key(cls, input_):
        t = cls.master_node.rpc('getrawtransaction', input_['txid'], True)
        return t['vout'][input_['vout']]['scriptPubKey']['hex']

    @classmethod
    def _utxo_to_utxo_details(cls, inputs):
        """Convert utxo to utxo details

        What are unspent transaction output (utxo) details?
        See: https://bitcoin.org/en/developer-reference#signrawtransaction

        """
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
        cls,
        sender,
        receiver,
        amount,
        output_asset_ids,
        utxo_details=[]
    ):
        # utxo_details specifies the outputs that are spent by this
        # transaction. When utxo_details are not supplied, any and
        # all outputs of the sender may be spent.
        inputs = cls._all_utxo(sender.address)
        outputs = {
            receiver.address: amount,
            'fee': DEFAULT_FEE,
            sender.address: sender.balance - DEFAULT_FEE - amount
        }
        txn_raw = cls._raw_transaction(inputs, outputs, output_asset_ids)
        utxo_details = utxo_details or cls._utxo_to_utxo_details(inputs)
        # XXX: what sense is there in having a transaction with
        # inputs that differ from the utxo_details? This would be a
        # transaction with inputs that are not spent by the
        # transaction.
        txn_signed = sender.sign(txn_raw, utxo_details)
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
    def _all_utxo(cls, address):
        """List all unspent transaction outputs for the address"""
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


@contextlib.contextmanager
def alice_and_bob():
    with Elements.node('master') as master_node:
        Wallet.master_node = master_node
        with Elements.node('alice') as node_alice:
            alice = Wallet(node_alice)
            alice.seed(SEED_AMOUNT)
            with Elements.node('bob') as node_bob:
                bob = Wallet(node_bob)
                bob.seed(SEED_AMOUNT)
                yield (alice, bob)


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
