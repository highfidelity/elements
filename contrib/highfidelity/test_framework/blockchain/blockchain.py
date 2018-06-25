import contextlib


class Blockchain:
    @classmethod
    @contextlib.contextmanager
    def node(
        cls,
        name,
        _warm_up_master=False,
        _ensure_signing_key=True,
        _pdb_on_exception=True,
        _debug=True
    ):
        raise NotImplementedError
