#!/usr/bin/env python3

# This started as the asset_tutorial.py.
# It now allows us to try a number of variations, but not combinations work. See "OPTIONS", below.
# Skip down to "START HERE", below, for the good stuff.

# To clean up after a failure:
# pkill elementsd bitcoind; rm -rf /tmp/e?

from test_framework.authproxy import AuthServiceProxy, JSONRPCException
import os
import random
import sys
import time
import subprocess
import shutil
from decimal import *
from pdb import set_trace
import timeit
import traceback
import pprint

pp = pprint.PrettyPrinter(indent=4)
def dp(a, b):  # debug pretty-printing
    pp.pprint([a, b])


## OPTIONS:

# Run with no arguments from the top of the elements directory.
# You can alternatively run with an argument of, e.g., ../bitcoin/src/bitcoind. See isbitcoin.
if len(sys.argv) >= 2:
    SIDECHAIN_PATH=sys.argv[1]
else:
    SIDECHAIN_PATH="./src/elementsd"

if len(sys.argv) == 3:  # specifically for pegin, below.
    MAINCHAIN_PATH=sys.argv[2]
else:
    MAINCHAIN_PATH="../bitcoin/src/bitcoind"

# The isbitcoin parts of the code illustrate the differences between bitcoin and elements.
isbitcoin = 'bitcoin' in SIDECHAIN_PATH

# Run in "regtest" rather than "main".
regtest = True

# True if we should use rpc.generate(n) to make explicit blocks, or false to getnewblockhex/signblock/submitblock
# The latter doesn't work in bitcoind (missing RPCs), but unsigned generate doesn't work in elements non-regtest. elements regtest can use either
do_unsigned_generate = isbitcoin #or regtest

# True does not seem to work unless you start with "enough" bitcoin on the PEGGED side (e.g., in regtest). See https://github.com/ElementsProject/elements/issues/285
# That seems to preclude use outside of regtest. They're working on a different pegin system.
pegin = False

# During speed test. Must be less than 20 or we run out of mempool.
transactions_per_block = 23

# True if we should keep alice and bob in a separate wallet. I.e, separate disconnected instances of elementsd (or bitcoind) being used as lightweight wallets.
use_separate_wallet = not pegin # doesn't work with pegin


print("isbitcoin:", isbitcoin, ", path:", SIDECHAIN_PATH, ", regtest:", regtest, ", generate() blocks:", do_unsigned_generate, ", pegin:", pegin, ", separate wallet:", use_separate_wallet, ", trans/block:", transactions_per_block)

def start_daemon(datadir, conf, args=""):
    if pegin:
        args += " -validatepegin"
    if regtest:
        args += " -regtest"
    subprocess.Popen((SIDECHAIN_PATH+" -datadir="+datadir+" "+args).split(), stdout=subprocess.PIPE)
    return AuthServiceProxy("http://"+conf["rpcuser"]+":"+conf["rpcpassword"]+"@127.0.0.1:"+conf["rpcport"])

def start_mainchain(datadir, conf, args=""):
    if not pegin:
        return
    if regtest:
        args += " -regtest"
    subprocess.Popen((MAINCHAIN_PATH+" -datadir="+datadir+" "+args).split(), stdout=subprocess.PIPE)
    return AuthServiceProxy("http://"+conf["rpcuser"]+":"+conf["rpcpassword"]+"@127.0.0.1:"+conf["rpcport"])

def loadConfig(filename):
    conf = {}
    with open(filename) as f:
        for line in f:
            if len(line) == 0 or line[0] == "#" or len(line.split("=")) != 2:
                continue
            conf[line.split("=")[0]] = line.split("=")[1].strip()
    conf["filename"] = filename
    return conf


## Preparations
# 1. Elements explicitly does not support chain=testnet, and I haven't been able to get custom to work, so for non-regtest, main it is.
# 2. The address network prefixes must match between node and wallet, so if we change the node network, the wallets must use the same.
confpath1 = os.path.dirname(__file__) + "/yelements1.conf"
confpath2 = os.path.dirname(__file__) + "/yelements2.conf"
confpath3 = os.path.dirname(__file__) + "/yelements3.conf"
confpathb = os.path.dirname(__file__) + "/bitcoin.conf"

# Make data directories for each daemon
e1_datadir="/tmp/e1"
e2_datadir="/tmp/e2"
e3_datadir="/tmp/e3"
eb_datadir="/tmp/eb"

os.makedirs(e1_datadir)
os.makedirs(e2_datadir)
os.makedirs(e3_datadir)
os.makedirs(eb_datadir)

# Also configure the nodes by copying the configuration files from
# this directory (and read them back for arguments):
shutil.copyfile(confpath1, e1_datadir+"/"+("bitcoin" if isbitcoin else "elements")+".conf")
shutil.copyfile(confpath2, e2_datadir+"/"+("bitcoin" if isbitcoin else "elements")+".conf")
shutil.copyfile(confpath3, e3_datadir+"/"+("bitcoin" if isbitcoin else "elements")+".conf")
shutil.copyfile(confpathb, eb_datadir+"/bitcoin.conf")

e1conf = loadConfig(confpath1)
e2conf = loadConfig(confpath2)
e3conf = loadConfig(confpath3)
ebconf = loadConfig(confpathb)

## Startup

if pegin:
    eb = start_mainchain(eb_datadir, ebconf)
    time.sleep(5)

e1 = start_daemon(e1_datadir, e1conf)
if use_separate_wallet:
    e2 = start_daemon(e2_datadir, e2conf)
    e3 = start_daemon(e3_datadir, e3conf)

time.sleep(12)  # why? how long? 6 seconds works when there is only one node. Seem to need 10 when there are three.
#e1.settxfee(0) # per kilobyte, not per transaction. A value of 1.0 seems to end up being 0.1 coin per transaction

dp("info", e1.getwalletinfo())

if not do_unsigned_generate:
    # get a block signing key for e1, and start over
    addr1 = e1.getnewaddress()
    valid1 = e1.validateaddress(addr1)
    pubkey1 = valid1["pubkey"]
    key1 = e1.dumpprivkey(addr1)
    e1.stop()
    time.sleep(2)
    signblockarg="-signblockscript=5121"+pubkey1+"51ae"

    # start over
    shutil.rmtree(e1_datadir)
    os.makedirs(e1_datadir)
    shutil.copyfile(confpath1, e1_datadir+"/"+("bitcoin" if isbitcoin else "elements")+".conf")
    e1 = start_daemon(e1_datadir, e1conf, signblockarg)
    time.sleep(10)

    e1.importprivkey(key1)
    dp("info after restart", e1.getwalletinfo())

def generate(n):
    if do_unsigned_generate:
        e1.generate(n)
        #print("block count after generating {0}: {1}".format(n, e1.getblockcount()))
        #dp("info after submitting signed", e1.getwalletinfo())
    else:
        # bitcoind allows generate to be used with signed blocks, but elementsd does not.
        # elementsd does allow the following manual block submission, but it is not clear if it is
        # supposed to produce a mining fee.
        # E.g., https://github.com/ElementsProject/elementsbp-api-reference/blob/master/api.md#getnewblockhex
        # says "The getnewblockhex RPC returns a new proposed (not mined) block."
        for count in range(0, n):
            # cannot use generate. must create/sign/submit a block
            blockhex = e1.getnewblockhex()
            sign1 = e1.signblock(blockhex)
            blockresult = e1.combineblocksigs(blockhex, [sign1])
            signedblock = blockresult["hex"]
            e1.submitblock(signedblock)
        #print("block count after submitting {0} signed: {1}".format(n, e1.getblockcount()))
        #dp("info after submitting signed", e1.getwalletinfo())

generate(101)
if pegin:
    #dp("main", eb.getwalletinfo())
    eb.generate(101)
    #dp("main after", eb.getwalletinfo())
    #dp("main unspent", eb.getbalance())

    e1.sendtomainchain(eb.getnewaddress(), 50.0) # FIXME
    addrs = e1.getpeginaddress()
    main_peg_address = addrs["mainchain_address"]
    side_peg_address = addrs["sidechain_address"]
    dp("peg addresses", addrs)
    txid = eb.sendtoaddress(main_peg_address, 25)
    #dp("main before spin", eb.getrawtransaction(txid, 1))
    eb.generate(102)
    #dp("main after spin", eb.getrawtransaction(txid, 1))
    #dp("unspent at mainchain address", eb.listunspent(0, 99999, [main_peg_address]))
    proof = eb.gettxoutproof([txid])
    #dp("proof", proof)
    raw = eb.getrawtransaction(txid)
    #dp("raw", raw)
    claimtxid = e1.claimpegin(raw, proof, side_peg_address)
    dp("confirmation", e1.getrawtransaction(claimtxid, 1))
    dp("local info", e1.getwalletinfo())
    new_wallet_balance = e1.getbalance()
    print("new wallet balance", new_wallet_balance)
    dp("unspent at claim address", e1.listunspent(0, 99999, [side_peg_address]))


### START HERE
# References:
# https://github.com/ElementsProject/elementsbp-api-reference/blob/master/api.md
# https://bitcoin.org/en/developer-reference#rpcs

## Operations and Utilities:

# The basic raw transaction mechanism.
def transact(inputs, outputs, debug = False, output_asset_ids = {}, signers = [{"signer": e1}]):

    if isbitcoin and len(inputs) > 0:
        # In Elements, we specify raw transaction outputs as:
        #   {address_1:amount_1, address_2:amount_2, ... "fee":fee_amount}
        # where the inputs must exactly must exactly match amount_1 + amount_2 + ... + fee_amount
        #
        # But bitcoin doesn't allow explicit "fee" outputs.
        # Instead, any input that isn't consumed by the outputs is considered the fee.
        # Here we adopt the convention that when testing in bitcoind, we strip the explicit "fee":fee_amount.
        bitcoin_outputs = {}
        for address, amount in outputs.items():
            if address != "fee":
                bitcoin_outputs[address] = amount
        outputs = bitcoin_outputs

    if debug:
        dp("inputs", inputs)
        dp("outputs", outputs)

    rawtx = e1.createrawtransaction(inputs, outputs, 1, output_asset_ids)

    #if debug: dp("created decoded", e1.decoderawtransaction(rawtx))

    if len(inputs) == 0: # Need to fund from the wallet rather than the (empty) inputs. Used for bootstrapping the test.
        rawtx = e1.fundrawtransaction(rawtx)["hex"]

    signedtx = rawtx
    for signer in signers:
        import pdb; pdb.set_trace()  # noqa
        details = signer["details"] if "details" in signer else getunspent_details(inputs)
        signedtx = signer["signer"].signrawtransaction(signedtx, details)["hex"]

    if debug: dp("signed decoded", e1.decoderawtransaction(signedtx))

    # Our units are such that the fixed transaction fee is supposed to be 1.
    # On a bitcoin scale, that's considered an absurdly-high-fee error. So second argument True to suppress.
    if isbitcoin:
        return e1.sendrawtransaction(signedtx, True) # Fewer allowed arguments
    else:
        return e1.sendrawtransaction(signedtx, True, True) # allow our fees, and do allow unblinded ouputs

# Elements creates blinded addresses by default. We're not using that (yet), so we need to "unblind" them.
def unblinded_address(rpc = e1):
    addr = rpc.getnewaddress()
    if not isbitcoin:  # Unblind it.
        addr = rpc.validateaddress(addr)["unconfidential"]
    return addr

if isbitcoin:
    money_asset_id = None
else:
    # Don't use the hex value from their examples! "b2e15d0d7a0c94e4e2ce0fe6e8691b9e451377f6e46e8045a86f7c4b5d4f0f23"
    # If you have a valid block signing program, the asset id for bitcoin magically changes to something else, which is different for each run!
    money_asset_id = "bitcoin"

MAX_CONFIRMATIONS = 9999999 # Need to specify the max old thing we care about. This is the default used by the daemons
MIN_CONFIRMATIONS = 0 # For our purposes, we'll take anything entered at all.
def listunspent(addresses, asset_id = money_asset_id, rpc = e1, list_unsafe = True):
    if isbitcoin:
        return rpc.listunspent(MIN_CONFIRMATIONS, MAX_CONFIRMATIONS, addresses)
    else:
        return rpc.listunspent(MIN_CONFIRMATIONS, MAX_CONFIRMATIONS, addresses, list_unsafe, asset_id)

# Addresses are not inputs to transactions. This gets an array of {txid, vout} pairs suitable for use as inputs.
def input_simple(input):
    txid = input["txid"]
    vout = input["vout"]
    return {"txid":txid, "vout":vout}

def getunspent(addresses, asset_id = money_asset_id, list_unsafe = True):
    listing = listunspent(addresses, asset_id, e1, list_unsafe)
    return list(map(input_simple, listing))

def input_detail(input):
    txid = input["txid"]
    vout = input["vout"]
    input_decoded = e1.getrawtransaction(txid, True)
    scriptPubKey = input_decoded["vout"][vout]["scriptPubKey"]
    return {"txid":txid, "vout":vout, "scriptPubKey":scriptPubKey["hex"]}

def getunspent_details(inputs):
    return list(map(input_detail, inputs))

seed_amount = 1000 if not isbitcoin else 20
bob_amount = 4
marketplace_amount = 2
fee_amount = 1
alice_change_amount = seed_amount - bob_amount - marketplace_amount - fee_amount

## Seeding:
marketplace = unblinded_address()
banker = unblinded_address()
if use_separate_wallet:
    bob_wallet = e2
    alice_wallet = e3
    bob = unblinded_address(bob_wallet)
    e1.importaddress(bob) # Track as a watch-only address, so that the main node can listunspent
    alice = unblinded_address(alice_wallet)
    alice_certs = unblinded_address(alice_wallet)
    e1.importaddress(alice)
    e1.importaddress(alice_certs)
else:
    bob_wallet = e1
    alice_wallet = e1
    bob = unblinded_address()
    alice = unblinded_address()
    # We need a different address for HFC and for certs. It isn't that they can't both be held at the same address, but that
    # Elements doesn't let us specify the asset type of outputs directly, but rather the asset type of addresses used in those outputs.
    # So if there it to be one atomic swap transaction, the buyer's change and the cert have to be delivered to different buyer addresses.
    alice_certs = unblinded_address()

# dp("just a send", e1.sendtoaddress(marketplace, 1, "comment ignored by Elements", "", False, money_asset_id, True))
# certdata = e1.issueasset(1, 1, False)
# cert_id_on_chain = certdata["asset"]
# dp("asset", certdata)
# dp("reissue", e1.reissueasset(certdata["asset"], 5))
# if not regtest:
#     dp("unspent", listunspent([]))
# dp("send", e1.sendtoaddress(marketplace, 1, "comment ignored by Elements", "", False, cert_id_on_chain, True))


# Start alice and bob with seed_amount units
transact([], {alice: seed_amount})
transact([], {bob: seed_amount})

## Example of normal operation:
## Alice buys a hat:

#generate(1)
inputs = getunspent([alice])
outputs = {bob: bob_amount,
           marketplace: marketplace_amount,
           alice: alice_change_amount,
           "data": "feed", # Transaction will include an asset with scriptPubKey {"type":"nulldata", "hex": "6a" + <n-bytes-loader> + <bytes>}
           "fee": fee_amount}
output_asset_ids = {}
signers = [{"signer": alice_wallet}]

if not isbitcoin:
    # If our own balance check for the user says we should make the sale, then make the cert and assign it to the marketplace,
    # unless we already have one from a previous failed sale.

    # Issuing and assigning the asset will have a transaction cost, paid from the wallet.
    # Alas, right now, alice, bob, and marketplace are also in the wallet, and might get raided for this purpose.
    # unless we lock them. This shouldn't be a problem if they are in separate wallets.
    locked = getunspent([alice, bob, marketplace])
    e1.lockunspent(False, locked)

    certdata = e1.issueasset(1, 0, False)
    cert_id_on_chain = certdata["asset"]
    dp("certificate asset id", cert_id_on_chain)
    # I don't know why this line is required. The getunspent finds cert_id_on_chain just fine without it, but later on the transaction
    # fill fail. Maybe issueasset is still too blinded, while sendtoaddress is not?
    # It's not a big deal to include this line. Just one micro-transaction fee.
    e1.sendtoaddress(marketplace, 1, "comment ignored by Elements", "", False, cert_id_on_chain, True)

    e1.lockunspent(True, locked)

    # Now add the cert to the big swap.
    # Note that the raw transaction will need two signers: One for alice's money (signed by alice_wallet), and one for the cert (signed by the marketplace)
    cert_inputs = getunspent([], cert_id_on_chain)
    signers[0]["details"] = getunspent_details(inputs)
    inputs += cert_inputs

    outputs[alice_certs] = 1
    output_asset_ids[alice_certs] = cert_id_on_chain
    signers.append({"signer": e1, "details": getunspent_details(cert_inputs)})

transact(inputs, outputs, False, output_asset_ids, signers)

if not isbitcoin: dp("unspent alice cert should be 1", listunspent([alice_certs], cert_id_on_chain))
bob_amount += seed_amount
dp("unspent alice money should be " + str(alice_change_amount), listunspent([alice]))
dp("unspent bob money should be " + str(bob_amount), listunspent([bob], money_asset_id))
dp("unspent marketplace money should be " + str(marketplace_amount), listunspent([marketplace]))

# Send money back and forth between alice and bob
# For each transer, we need to get the new unspent at the address (following the last transfer), sign, and submit.
# So there's a lot of stuff going on.
def ping_pong(data):
    amount = 3
    inputs = getunspent([bob], money_asset_id)
    data["alice"] += amount
    data["bob"] -= (amount + 1)
    outputs = {alice: amount, "fee": 1, bob: data["bob"]}
    transact(inputs, outputs, False, {}, [{"signer": bob_wallet}])
    if transactions_per_block == 1: generate(1)

    inputs = getunspent([alice], money_asset_id)
    data["alice"] -= (amount + 1)
    data["bob"] += amount
    outputs = {bob: amount, "fee": 1, alice: data["alice"]}
    transact(inputs, outputs, False, {}, [{"signer": alice_wallet}])

    if transactions_per_block <= 2:
        generate(1)
    else:
        data["count"] += 2;
        if data["count"] > transactions_per_block:
            generate(1)
            data["count"] = 0

def wrapper(func, *args, **kwargs):
    def wrapped():
        return func(*args, **kwargs)
    return wrapped

generate(1)
data = {"alice": alice_change_amount, "bob": bob_amount, "count": 0}
wrapped = wrapper(ping_pong, data)
tries = 100 if not isbitcoin else 13 # bitcoin gets out of range (out of money?) with any higher
seconds = timeit.timeit(wrapped, number=tries)
print("timed {0} in {1}, {2} transactions/second".format(tries * 2, seconds, (2 * tries) / seconds))

# Here we try to set up as much as we can outside of the timed part.
# We set up an array of addresses (as if they were perhaps different people),
# put a little money in each,
# prepare a signed transmission
# and then time just the submission and possible block generation.


## Shutdown

e1.stop()
if use_separate_wallet:
    e2.stop()
    e3.stop()
if pegin:
    eb.stop()
time.sleep(5)
shutil.rmtree(e1_datadir)
shutil.rmtree(e2_datadir)
shutil.rmtree(e3_datadir)
shutil.rmtree(eb_datadir)
