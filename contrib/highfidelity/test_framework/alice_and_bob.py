import contextlib

from .blockchain import Elements
from .wallet import Wallet, SEED_AMOUNT


@contextlib.contextmanager
def alice_and_bob(blockchain=Elements, debug=True):
    with blockchain.node('master', _debug=debug) as master_node:
        Wallet.master_node = master_node
        with blockchain.node('alice', _debug=debug) as node_alice:
            alice = Wallet(node_alice)
            alice.seed(SEED_AMOUNT)
            with blockchain.node('bob', _debug=debug) as node_bob:
                bob = Wallet(node_bob)
                bob.seed(SEED_AMOUNT)
                Wallet.master_node.generate_block()
                yield (alice, bob)
