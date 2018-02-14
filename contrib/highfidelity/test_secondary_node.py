import time

import pytest

from .blockchain import Elements, EOS


def test_nodes_see_all_transactions(blockchain):
    # All nodes on a blockchain see all transactions. Think of these
    # transactions as "proposed" lines in a giant public ledger book
    with blockchain.nodes() as nodes:
        nodes[0].create_transactions(10)
        time.sleep(1)
        assert nodes[0].transactions == nodes[1].transactions


def test_nodes_see_all_created_blocks(blockchain):
    # All nodes on a blockchain see all "created blocks". Think of these
    # as written pages in the giant public ledger book, once written
    # down they can never be changed.
    with blockchain.nodes() as nodes:
        nodes[0].create_blocks(10)
        time.sleep(1)
        assert nodes[0].blocks == nodes[1].blocks


def test_nodes_have_a_copy_of_the_current_blockchain(blockchain):
    with blockchain.nodes() as nodes:
        nodes[0].create_blockchain(total_blocks=10)
        time.sleep(1)
        assert nodes[0].blockchain == nodes[1].blockchain


def test_nodes_obey_the_same_rules(blockchain):
    # All nodes share a common set of rules about which transactions
    # should be approved and as a result what an expected or "validated
    # block" will look like given the current pending list of proposed
    # transactions.
    with blockchain.nodes() as nodes:
        # Ensure nodes cooperate at all.
        nodes[0].create_blocks(1)
        time.sleep(1)
        assert nodes[0].blocks == nodes[1].blocks
        # Ensure that node 1 refuses to cooperate given a bad block.
        nodes[0].commit_bad_block()
        time.sleep(1)
        assert 2 == len(nodes[0].blocks)
        assert 1 == len(nodes[1].blocks)


def test_nodes_are_validators(blockchain):
    # Node forks if and when a created block violates the commomn set of
    # rules.
    with blockchain.nodes() as nodes:
        nodes[0].create_blocks(10)
        time.sleep(1)
        assert nodes[0].blocks == nodes[1].blocks
        nodes[0].commit_bad_block()  # node[1] forks!
        nodes[0].create_blocks(10)
        time.sleep(1)
        assert 21 == len(nodes[0].blocks)
        assert 10 == len(nodes[1].blocks)


@pytest.mark.skip(reason='Outside current requirements')
def test_multiple_signers(blockchain):
    raise NotImplementedError


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


def test_second_node_cannot_add_transactions(blockchain):
    with blockchain.nodes() as nodes:
        with pytest.raises(nodes[1].CannotAddTransactionError):
            nodes[1].create_transactions(1)
