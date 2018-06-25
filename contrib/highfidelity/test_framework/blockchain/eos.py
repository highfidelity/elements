from .blockchain import Blockchain


class EOS(Blockchain):
    def _start_nodes(self):
        raise NotImplementedError

    def _stop_nodes(self):
        raise NotImplementedError
