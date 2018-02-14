import contextlib


class Blockchain:
    class Error(Exception): pass  # noqa: E701
    class CannotAddTransactionError(Error): pass  # noqa: E301, E701

    def __init__(self):
        self._nodes = None

    @contextlib.contextmanager
    def nodes(self):
        self._start_nodes()
        yield self._nodes
        self._stop_nodes()

    def _start_nodes(self):
        raise NotImplementedError

    def _stop_nodes(self):
        raise NotImplementedError
