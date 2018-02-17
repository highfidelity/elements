import contextlib
import logging
import os
import shutil
import subprocess
import tempfile
import time

from ..test_framework.authproxy import AuthServiceProxy, JSONRPCException
from .blockchain import Blockchain
from .error import Error

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
        class FailedToGenerateBlockError(Error): pass  # noqa: E301, E701
        class MissingConfigKeysError(Error): pass  # noqa: E301, E701

        MAX_RETRIES = 5

        _logger = logging.getLogger('Node')

        def __init__(self, name, total_attempts=5, interval_seconds=2.0):
            self.name = name
            self._is_up = False
            self._proxy = None

        def rpc(self, command, *args):
            self._ensure_is_up()
            return getattr(self._proxy, command)(*args)

        def generate_block(self):
            blockhex = self.rpc('getnewblockhex')
            sign1 = self.rpc('signblock', blockhex)
            blockresult = self.rpc('combineblocksigs', blockhex, [sign1])
            signedblock = blockresult["hex"]
            return self.rpc('submitblock', signedblock)

        def _auth_service_proxy(self):
            config = self._load_config()
            proxy_url = f'http://{config["rpcuser"]}:{config["rpcpassword"]}@127.0.0.1:{config["rpcport"]}'  # noqa: E501
            return AuthServiceProxy(proxy_url)

        def _load_config(self):
            filename = config_filepath(self.name)
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

        def _ensure_is_up(self):
            if None is self._proxy:
                self._proxy = self._auth_service_proxy()
            if not self._is_up:
                for _ in range(5):
                    try:
                        self._proxy.ping()
                    except ConnectionRefusedError:
                        logging.debug('waiting for daemon to start...')
                        time.sleep(1)
                        self._proxy = self._auth_service_proxy()
                    except JSONRPCException as e:
                        msg = f'daemon started but is not ready: {e.error}'
                        logging.debug(msg)
                        time.sleep(1)
                        self._proxy = self._auth_service_proxy()
                    else:
                        self._is_up = True
                        return
                raise ConnectionRefusedError('giving up; daemon unavailable')

    @classmethod
    @contextlib.contextmanager
    def node(cls, name, _warm_up_master=False, _ensure_signing_key=True):
        if _ensure_signing_key:
            cls._ensure_signing_key()
        try:
            with tempfile.TemporaryDirectory() as datadir:
                process = cls._spawn_node_process(name, datadir)
                node = cls.Node(name)
                if 'master' == name:
                    if _warm_up_master:
                        cls._logger.info('pause after starting master...')
                        time.sleep(5)
                    node.rpc('importprivkey', cls.signing_privkey)
                    cls._generate_initial_signed_blocks(node)
                yield node
                cls._stop_node_process(process, node)
        except OSError as e:
            # The daemon may continue writing to the datadir and so
            # TemporaryDirectory's attempt to clean up the directory
            # may fail. Ignore this.
            #
            # 66 corresponds to "Directory not empty".
            if 66 != e.errno:
                raise
        cls._logger.info(f'pause after terminating {node.name}...')
        time.sleep(2)

    @classmethod
    def _generate_initial_signed_blocks(cls, node):
        for _ in range(101):
            result = node.generate_block()
            if result:
                raise cls.FailedToGenerateBlockError(result)

    @classmethod
    def _ensure_signing_key(cls):
        if not cls.signing_pubkey:
            with cls.node(
                'bootstrap_signing_key',
                _ensure_signing_key=False
            ) as node:
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
    def _stop_node_process(cls, process, node):
        node.rpc('stop')
        cls._logger.info(f'waiting for {node.name} to halt...')
        process.wait()
        cls._logger.info(f'{node.name} halted')
