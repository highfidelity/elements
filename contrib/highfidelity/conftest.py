# Configure test parameters
# See: https://docs.pytest.org/en/latest/example/parametrize.html

from .blockchain import Elements, EOS


ALL_BLOCKCHAINS = [Elements, EOS]


def pytest_addoption(parser):
    parser.addoption('--elements', action='store_true', help='limit tests to Elements')  # noqa: E501
    parser.addoption('--eos', action='store_true', help='limit tests to EOS')


def pytest_generate_tests(metafunc):
    if 'blockchain' in metafunc.fixturenames:
        config = metafunc.config
        blockchains = list()
        if config.getoption('elements'):
            blockchains.append(Elements())
        if config.getoption('eos'):
            blockchains.append(EOS())
        if not blockchains:
            blockchains = [blockchain() for blockchain in ALL_BLOCKCHAINS]
        metafunc.parametrize('blockchain', blockchains)
