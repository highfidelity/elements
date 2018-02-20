import logging
import time

import pytest

from .test_framework.alice_and_bob import alice_and_bob
from .test_framework.kill_elementsd_before_each_function import *  # noqa: E501, F401, F403


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('test_explorer_node')


def _wait_for(function):
    for _ in range(5):
        if not function():
            time.sleep(1)
        else:
            return
    raise TimeoutError


def test_slave_sees_all_blocks_and_transactions(blockchain):
    # All nodes on a blockchain see all transactions. Think of these
    # transactions as "proposed" lines in a giant public ledger book
    with alice_and_bob(blockchain) as (alice, bob):
        with blockchain.node('slave') as slave:
            master = alice.master_node  # or bob.master_node; same thing

            # Wait for master-slave connection.
            _wait_for(lambda: 1 == master.rpc('getinfo')['connections'])
            last_block = master.rpc('listsinceblock')['lastblock']

            # Wait for slave to sync initial blockchain from master.
            _wait_for(
                lambda: last_block == slave.rpc('listsinceblock')['lastblock'])  # noqa: E501

            # Confirm that slave is aware of unconfirmed transactions.
            rawmempool = master.rpc('getrawmempool')
            _wait_for(lambda: rawmempool == slave.rpc('getrawmempool'))

            # Generate and verify existence of a new block.
            master.generate_block()
            last_block_new = master.rpc('listsinceblock')['lastblock']
            assert last_block != last_block_new

            # Verify that all transactions have been confirmed.
            assert 0 == len(master.rpc('getrawmempool'))

            # Wait for new block to propagate to slave.
            expected = last_block_new
            _wait_for(
                lambda: expected == slave.rpc('listsinceblock')['lastblock'])

            # Ensure that slave has no uncommited transactions.
            assert 0 == len(slave.rpc('getrawmempool'))


@pytest.mark.skip
def test_nodes_obey_the_same_rules(blockchain):
    # All nodes share a common set of rules about which transactions
    # should be approved and as a result what an expected or "validated
    # block" will look like given the current pending list of proposed
    # transactions.
    with blockchain.nodes() as (master, slave):
        # Ensure nodes cooperate at all.
        master.create_blocks(1)
        time.sleep(1)
        assert master.blocks == slave.blocks
        # Ensure that node 1 refuses to cooperate given a bad block.
        master.commit_bad_block()
        time.sleep(1)
        assert 2 == len(master.blocks)
        assert 1 == len(slave.blocks)


@pytest.mark.skip
def test_nodes_are_validators(blockchain):
    # Node forks if and when a created block violates the commomn set of
    # rules.
    with blockchain.nodes() as (master, slave):
        master.create_blocks(10)
        time.sleep(1)
        assert master.blocks == slave.blocks
        master.commit_bad_block()  # node[1] forks!
        master.create_blocks(10)
        time.sleep(1)
        assert 21 == len(master.blocks)
        assert 10 == len(slave.blocks)


@pytest.mark.skip(reason='Outside current requirements')
def test_multiple_signers(blockchain):
    raise NotImplementedError


@pytest.mark.skip
def test_multiple_block_creators(blockchain):
    if blockchain is Elements:
        # TL;DR -- There is nothing to test in this case.
        #
        # Elements does not have native support for multiple block
        # creators.
        #
        #   - There are ways to build this functionality externally to the
        #     elements code base, but it is a non-trivial project.
        #
        #   - Elements claims to have this feature on their roadmap for
        #     June 2018, they previously estimated Q1 2018.
        #
        #   - Elements is considering allowing non-open source licensing
        #     of some of their technology to do this, and are "working
        #     on a proposal for us"
        pass
    if blockchain is EOS:
        raise NotImplementedError


@pytest.mark.skip
def test_second_node_cannot_add_transactions(blockchain):
    with blockchain.nodes() as (master, slave):
        with pytest.raises(slave.CannotAddTransactionError):
            slave.create_transactions(1)
