import contextlib

from ..error import Error


class Blockchain:
    class CannotAddTransactionError(Error):
        pass

    @classmethod
    @contextlib.contextmanager
    def node_pair(cls):
        with cls.node('master') as master:
            with cls.node('slave') as slave:
                yield master, slave

    @classmethod
    @contextlib.contextmanager
    def node(cls, daemon_name):
        raise NotImplementedError
