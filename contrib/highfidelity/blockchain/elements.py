import contextlib
import logging
import os
import shutil
import subprocess
import tempfile
import time

from ..test_framework.authproxy import AuthServiceProxy
from .blockchain import Blockchain
from .error import Error
# from .node import Node

# -connect=<ip> -- connect only to the specified node
# -bind=<addr> -- bind to given address and always listen
# -dns=0 -- disable dns lookups for connect
# -blockmaxsize=0 -- the maximum block size in bytes
# -disablewallet -- ??? do not load the wallet and disable wallet RPC calls


REQUIRED_CONFIG_KEYS = {'rpcuser', 'rpcpassword', 'rpcport'}


def config_filepath(node_name):
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f'elements.{node_name}.conf')


class Elements(Blockchain):
    class NodeFailedToStartError(Error): pass  # noqa: E701

    signing_pubkey = None
    signing_privkey = None

    _logger = logging.getLogger('Elements')

    class Node:
        class CannotConnectError(Error): pass  # noqa: E701
        class CannotExecuteRpcError(Error): pass  # noqa: E301, E701
        class MissingConfigKeysError(Error): pass  # noqa: E301, E701

        MAX_RETRIES = 5

        _logger = logging.getLogger('Node')

        def __init__(self, node_name, total_attempts=5, interval_seconds=2.0):
            self._proxy = self._auth_service_proxy(node_name)

        def rpc(self, name, *args):
            return getattr(self._proxy, name)(*args)

        def _auth_service_proxy(self, node_name):
            config = self._load_config(node_name)
            proxy_url = f'http://{config["rpcuser"]}:{config["rpcpassword"]}@127.0.0.1:{config["rpcport"]}'  # noqa: E501
            return AuthServiceProxy(proxy_url)

        def _load_config(self, node_name):
            filename = config_filepath(node_name)
            with open(filename, 'r') as file:
                config = self._config_from_file(filename, file)
            self._check_for_required_config_keys(set(config.keys()), filename)
            return {k: config[k] for k in REQUIRED_CONFIG_KEYS}

        def _config_from_file(self, filename, file):
            config = {'filename': filename}
            for line in file:
                if line and '#' != line[0] and 2 == len(line.split('=')):
                    key, value = line.strip().split('=')
                    config[key] = value
            return config

        def _check_for_required_config_keys(self, config_keys, filename):
            missing_config_keys = REQUIRED_CONFIG_KEYS - config_keys
            if missing_config_keys:
                raise self.MissingConfigKeysError(
                    f'{filename} is missing {missing_config_keys}')

    @classmethod
    @contextlib.contextmanager
    def node(cls, node_name, _ensure_signing_key=True):
        if _ensure_signing_key:
            cls._ensure_signing_key()
        with tempfile.TemporaryDirectory() as datadir:
            process = cls._spawn_node_process(node_name, datadir)
            time.sleep(10)
            node = cls.Node(node_name)
            if 'master' == node_name:
                node.rpc('importprivkey', cls.signing_privkey)
                cls._generate_initial_signed_blocks(node)
            yield node
            cls._stop_node_process(process, node, node_name)

    @classmethod
    def _generate_initial_signed_blocks(cls, proxy):
        for _ in range(101):
            cls._generate_block(proxy)

    @classmethod
    def _generate_block(cls, proxy):
        blockhex = proxy.rpc('getnewblockhex')
        sign1 = proxy.rpc('signblock', blockhex)
        blockresult = proxy.rpc('combineblocksigs', blockhex, [sign1])
        signedblock = blockresult["hex"]
        proxy.rpc('submitblock', signedblock)

    @classmethod
    def _ensure_signing_key(cls):
        if not cls.signing_pubkey:
            with cls.node('bootstrap_signing_key', False) as node:
                address = node.rpc('getnewaddress')
                result = node.rpc('validateaddress', address)
                assert result['isvalid']
                cls.signing_pubkey = result['pubkey']
                cls.signing_privkey = node.rpc('dumpprivkey', address)

    @classmethod
    def _spawn_node_process(cls, node_name, datadir):
        cls._configure_node_process(node_name, datadir)
        elementsd_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            '..', '..', '..', 'src', 'elementsd')
        cls._logger.info(f'starting {node_name}...')
        args = [f'-datadir={datadir}', '-regtest']
        if 'master' == node_name:
            args.append(f'-signblockscript=5121{cls.signing_pubkey}51ae')
        return subprocess.Popen([elementsd_path, *args])

    @classmethod
    def _configure_node_process(cls, node_name, datadir):
        src = config_filepath(node_name)
        dest = os.path.join(datadir, 'elements.conf')
        shutil.copyfile(src, dest)

    @classmethod
    def _stop_node_process(cls, process, proxy, node_name):
        proxy.rpc('stop')
        cls._logger.info(f'waiting for {node_name} to halt...')
        process.wait()
        cls._logger.info(f'{node_name} halted')
