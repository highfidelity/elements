from .blockchain import Blockchain

# -connect=<ip> -- connect only to the specified node
# -bind=<addr> -- bind to given address and always listen
# -dns=0 -- disable dns lookups for connect
# -blockmaxsize=0 -- the maximum block size in bytes
# -disablewallet -- ??? do not load the wallet and disable wallet RPC calls


class Elements(Blockchain):
    def _start_nodes(self):
        raise NotImplementedError

    def _stop_nodes(self):
        raise NotImplementedError
