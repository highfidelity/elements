import contextlib


class Blockchain:
    @classmethod
    @contextlib.contextmanager
    def node(cls, daemon_name):
        raise NotImplementedError
