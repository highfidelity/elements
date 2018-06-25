import decimal

from .error import Error

# MONEY_ASSET_ID = 'bitcoin'
DEFAULT_FEE = 1
MAX_CONFIRMATIONS = 9999999  # This is the default used by the daemons.
MIN_CONFIRMATIONS = 0  # Accept unconfirmed transactions during testing.
SEED_AMOUNT = 1000


class Wallet:
    class InvalidWalletBalance(Error): pass  # noqa: E701

    master_node = None

    def __init__(self, node):
        # We do not have an implementation of a lightweight wallet
        # for generating and storing keys and signing transactions.
        # As a quick hack in testing we use a full node for this
        # purpose. And since our tests monitor transaction activity
        # at the master node, we register all wallet-related
        # addresses as watch-only address at the master node.
        self._node = node
        self._initialize_address()
        self._expected_balance = 0

    @property
    def balance(self):
        """Validate and return the wallet's balance."""
        result = sum(
            x['amount'] for x in self._all_utxo(self.address))
        if self._expected_balance != result:
            self.InvalidWalletBalance(self.address)
        return result

    @classmethod
    def transact(
        cls,
        sender,
        receiver,
        amount,
        output_asset_ids={},
        utxo_details=[]
    ):
        # utxo_details are unspent transaction outputs
        assert isinstance(amount, (int, decimal.Decimal))
        if sender:
            result = cls._transact(
                sender, receiver, amount, output_asset_ids, utxo_details)
            sender._expected_balance -= amount + DEFAULT_FEE
            receiver._expected_balance += amount
        else:
            result = cls._airdrop(receiver, amount)
            receiver._expected_balance += amount
        return result

    def seed(self, amount):
        self.transact(None, self, amount)

    def sign(self, raw_transaction, utxo_details=None):
        """Sign a raw transaction

        Arguments:
            raw_transaction (hex): the transaction to sign as a
                serialized transaction
            utxo_details (list; optional): The previous outputs being
                spent by this transaction

        For more information on utxo_details, see:
            https://bitcoin.org/en/developer-reference#signrawtransaction

        """
        return self._node.rpc(
            'signrawtransaction', raw_transaction, utxo_details)['hex']

    # def certify(self, item_id):
    #     assert 'item_id' not in self.certificates
    #     self.certificates[item_id] = self._unconfidential_address()
    #     self._master_node.importaddress(self.certificates[item_id])

    @classmethod
    def _script_pub_key(cls, input_):
        t = cls.master_node.rpc('getrawtransaction', input_['txid'], True)
        return t['vout'][input_['vout']]['scriptPubKey']['hex']

    @classmethod
    def _utxo_to_utxo_details(cls, inputs):
        """Convert utxo to utxo details

        What are unspent transaction output (utxo) details?
        See: https://bitcoin.org/en/developer-reference#signrawtransaction

        """
        result = list()
        for input_ in inputs:
            result.append({
                'txid': input_['txid'],
                'vout': input_['vout'],
                'scriptPubKey': cls._script_pub_key(input_)
            })
        return result

    @classmethod
    def _transact(
        cls,
        sender,
        receiver,
        amount,
        output_asset_ids,
        utxo_details=[]
    ):
        # utxo_details specifies the outputs that are spent by this
        # transaction. When utxo_details are not supplied, any and
        # all outputs of the sender may be spent.
        inputs = cls._all_utxo(sender.address)
        outputs = {
            receiver.address: amount,
            'fee': DEFAULT_FEE,
            sender.address: sender.balance - DEFAULT_FEE - amount
        }
        txn_raw = cls._raw_transaction(inputs, outputs, output_asset_ids)
        utxo_details = utxo_details or cls._utxo_to_utxo_details(inputs)
        # XXX: what sense is there in having a transaction with
        # inputs that differ from the utxo_details? This would be a
        # transaction with inputs that are not spent by the
        # transaction.
        txn_signed = sender.sign(txn_raw, utxo_details)
        return cls.master_node.rpc('sendrawtransaction', txn_signed, True, True)  # noqa: E501

    @classmethod
    def _airdrop(cls, receiver, amount):
        inputs = []
        outputs = {receiver.address: amount}
        txn_raw = cls._raw_transaction(inputs, outputs)
        txn_funded = cls.master_node.rpc(
            'fundrawtransaction', txn_raw)['hex']
        txn_signed = cls.master_node.rpc(
            'signrawtransaction', txn_funded)['hex']
        return cls.master_node.rpc(
            'sendrawtransaction', txn_signed, True, True)

    @classmethod
    def _raw_transaction(cls, inputs, outputs, output_asset_ids={}):
        return cls.master_node.rpc(
            'createrawtransaction',
            inputs,
            outputs,
            1,  # Why 1? Why not 0?
            output_asset_ids)

    @classmethod
    def _all_utxo(cls, address):
        """List all unspent transaction outputs for the address"""
        return cls.master_node.rpc(
            'listunspent',
            MIN_CONFIRMATIONS,
            MAX_CONFIRMATIONS,
            [address])

    def _initialize_address(self):
        self.address = self._unconfidential_address()
        self.master_node.rpc('importaddress', self.address)

    def _unconfidential_address(self):
        address_new = self._node.rpc('getnewaddress')
        address_validated = \
            self._node.rpc('validateaddress', address_new)
        return address_validated['unconfidential']
