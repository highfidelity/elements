import logging
import os
import time

import pytest

from .blockchain import Elements, EOS


logging.basicConfig()


def setup_function(function):
    os.system('pkill elementsd')
    time.sleep(1)


def teardown_module(module):
    os.system('pkill elementsd')
    time.sleep(1)


def test_nodes_see_all_transactions(blockchain):
    # All nodes on a blockchain see all transactions. Think of these
    # transactions as "proposed" lines in a giant public ledger book
    with blockchain.node_pair() as (master, slave):
        pass
#         master.create_transactions(10)
#         time.sleep(1)
#         assert master.transactions == slave.transactions


# def test_nodes_see_all_created_blocks(blockchain):
#     # All nodes on a blockchain see all "created blocks". Think of these
#     # as written pages in the giant public ledger book, once written
#     # down they can never be changed.
#     with blockchain.nodes() as (master, slave):
#         master.create_blocks(10)
#         time.sleep(1)
#         assert master.blocks == slave.blocks


# def test_nodes_have_a_copy_of_the_current_blockchain(blockchain):
#     with blockchain.nodes() as (master, slave):
#         master.create_blockchain(total_blocks=10)
#         time.sleep(1)
#         assert master.blockchain == slave.blockchain


# def test_nodes_obey_the_same_rules(blockchain):
#     # All nodes share a common set of rules about which transactions
#     # should be approved and as a result what an expected or "validated
#     # block" will look like given the current pending list of proposed
#     # transactions.
#     with blockchain.nodes() as (master, slave):
#         # Ensure nodes cooperate at all.
#         master.create_blocks(1)
#         time.sleep(1)
#         assert master.blocks == slave.blocks
#         # Ensure that node 1 refuses to cooperate given a bad block.
#         master.commit_bad_block()
#         time.sleep(1)
#         assert 2 == len(master.blocks)
#         assert 1 == len(slave.blocks)


# def test_nodes_are_validators(blockchain):
#     # Node forks if and when a created block violates the commomn set of
#     # rules.
#     with blockchain.nodes() as (master, slave):
#         master.create_blocks(10)
#         time.sleep(1)
#         assert master.blocks == slave.blocks
#         master.commit_bad_block()  # node[1] forks!
#         master.create_blocks(10)
#         time.sleep(1)
#         assert 21 == len(master.blocks)
#         assert 10 == len(slave.blocks)


# @pytest.mark.skip(reason='Outside current requirements')
# def test_multiple_signers(blockchain):
#     raise NotImplementedError


# def test_multiple_block_creators(blockchain):
#     if blockchain is Elements:
#         # TL;DR -- There is nothing to test in this case.
#         #
#         # Elements does not have native support for multiple block
#         # creators.
#         #
#         #   - There are ways to build this functionality externally to the
#         #     elements code base, but it is a non-trivial project.
#         #
#         #   - Elements claims to have this feature on their roadmap for
#         #     June 2018, they previously estimated Q1 2018.
#         #
#         #   - Elements is considering allowing non-open source licensing
#         #     of some of their technology to do this, and are "working
#         #     on a proposal for us"
#         pass
#     if blockchain is EOS:
#         raise NotImplementedError


# def test_second_node_cannot_add_transactions(blockchain):
#     with blockchain.nodes() as (master, slave):
#         with pytest.raises(slave.CannotAddTransactionError):
#             slave.create_transactions(1)
