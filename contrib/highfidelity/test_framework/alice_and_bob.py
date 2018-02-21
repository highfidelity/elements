import contextlib

from .blockchain import Elements
from .wallet import Wallet, SEED_AMOUNT


@contextlib.contextmanager
def alice_and_bob(blockchain=Elements):
    with blockchain.node('master') as master_node:
        Wallet.master_node = master_node
        with blockchain.node('alice') as node_alice:
            alice = Wallet(node_alice)
            alice.seed(SEED_AMOUNT)
            with blockchain.node('bob') as node_bob:
                bob = Wallet(node_bob)
                bob.seed(SEED_AMOUNT)
                Wallet.master_node.generate_block()
                yield (alice, bob)