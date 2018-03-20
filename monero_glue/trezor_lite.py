#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Dusan Klinec, ph4r05, 2018

import binascii

from monero_serialize import xmrtypes, xmrserialize
from .monero import TsxData, classify_subaddresses, addr_to_hash
from . import monero, crypto, ring_ct, mlsag2
from . import common as common
from . import trezor


class TrezorLite(object):
    """
    Main Trezor object
    """
    def __init__(self):
        self.tsx_ctr = 0
        self.tsx_obj = None  # type: TTransaction
        self.creds = None  # type: trezor.WalletCreds

    async def init_transaction(self, tsx_data: TsxData):
        self.tsx_ctr += 1
        self.tsx_obj = TTransaction(self)
        self.tsx_obj.creds = self.creds
        return await self.tsx_obj.init_transaction(tsx_data, self.tsx_ctr)

    async def precompute_subaddr(self, account, indices):
        """
        Precomputes subaddresses for account (major) and list of indices (minors)
        :param account:
        :param indices:
        :return:
        """
        return self.tsx_obj.precompute_subaddr(account, indices)

    async def set_input_count(self, inp_cnt):
        """
        :param inp_cnt
        :return:
        """
        return await self.tsx_obj.set_input_cnt(inp_cnt)

    async def set_tsx_input(self, src_entr):
        """
        :param src_entr
        :type src_entr: xmrtypes.TxSourceEntry
        :return:
        """
        return await self.tsx_obj.set_input(src_entr)

    async def tsx_inputs_done(self):
        """
        All inputs set
        :return:
        """
        return await self.tsx_obj.tsx_inputs_done()

    async def tsx_inputs_permutation(self, permutation):
        """
        All inputs set
        :return:
        """
        return await self.tsx_obj.tsx_inputs_permutation(permutation)

    async def tsx_input_vini(self, *args, **kwargs):
        """
        All inputs set
        :return:
        """
        return await self.tsx_obj.tsx_input_vini(*args, **kwargs)

    async def tsx_input_vini_done(self, *args, **kwargs):
        """
        All inputs set
        :return:
        """
        return await self.tsx_obj.tsx_input_vini_done(*args, **kwargs)

    async def set_tsx_output1(self, dst_entr):
        """
        :param src_entr
        :type src_entr: xmrtypes.TxDestinationEntry
        :return:
        """
        return await self.tsx_obj.set_out1(dst_entr)

    async def all_out1_set(self):
        """
        :return:
        """
        return await self.tsx_obj.all_out1_set()


class TState(object):
    """
    Transaction state
    """
    def __init__(self):
        self.s = 0
        self.in_mem = False

    def init_tsx(self):
        self.s = 1

    def precomp(self):
        if self.s != 1:
            raise ValueError('Illegal state')
        self.s = 2

    def inp_cnt(self, in_mem):
        if self.s != 2:
            raise ValueError('Illegal state')
        self.s = 3
        self.in_mem = in_mem

    def input(self):
        if self.s != 3 and self.s != 4:
            raise ValueError('Illegal state')
        self.s = 4

    def input_done(self):
        if self.s != 4:
            raise ValueError('Illegal state')
        self.s = 5

    def input_permutation(self):
        if self.in_mem or self.s != 5:
            raise ValueError('Illegal state')
        self.s = 6

    def input_vins(self):
        if self.in_mem or (self.s != 6 and self.s != 7):
            raise ValueError('Illegal state')
        self.s = 7

    def input_vins_done(self):
        if self.in_mem or self.s != 7:
            raise ValueError('Illegal state')
        self.s = 8

    def set_output(self):
        if ((not self.in_mem and self.s != 7) or (self.in_mem and self.s != 5)) and self.s != 9:
            raise ValueError('Illegal state')
        self.s = 9

    def set_output_done(self):
        if self.s != 9:
            raise ValueError('Illegal state')
        self.s = 10


class TTransaction(object):
    """
    Transaction builder
    """
    def __init__(self, trezor=None):
        self.trezor = trezor  # type: Trezor
        self.creds = None  # type: WalletCreds
        self.key_master = None
        self.key_hmac = None

        self.r = None  # txkey
        self.r_pub = None
        self.state = TState()

        self.tsx_data = None  # type: monero.TsxData
        self.need_additional_txkeys = False
        self.use_bulletproof = False
        self.use_rct = True
        self.use_simple_rct = False
        self.input_count = 0
        self.additional_tx_keys = []
        self.additional_tx_public_keys = []
        self.inp_idx = -1
        self.out_idx = -1
        self.summary_inputs_money = 0
        self.summary_outs_money = 0
        self.input_rcts = []
        self.input_secrets = []
        self.output_secrets = []
        self.output_amounts = []
        self.subaddresses = {}
        self.tx = xmrtypes.Transaction(vin=[], vout=[], extra=[])
        self.source_permutation = []  # sorted by key images
        self.tx_prefix_hasher = common.KeccakArchive()
        self.tx_prefix_hash = None

    def gen_r(self):
        """
        Generates a new transaction key pair.
        :return:
        """
        self.r = crypto.random_scalar()
        self.r_pub = crypto.scalarmult_base(self.r)

    async def init_transaction(self, tsx_data, tsx_ctr):
        """
        Initializes a new transaction.
        :param tsx_data:
        :param tsx_ctr:
        :return:
        """
        self.tsx_data = tsx_data
        self.gen_r()
        self.state.init_tsx()

        # Additional keys
        class_res = classify_subaddresses(tsx_data.outputs, tsx_data.change_dts.addr if tsx_data.change_dts else None)
        num_stdaddresses, num_subaddresses, single_dest_subaddress = class_res

        # if this is a single-destination transfer to a subaddress, we set the tx pubkey to R=s*D
        if num_stdaddresses == 0 and num_subaddresses == 1:
            self.r_pub = crypto.ge_scalarmult(self.r, crypto.decodepoint(single_dest_subaddress.m_spend_public_key))

        self.need_additional_txkeys = num_subaddresses > 0 and (num_stdaddresses > 0 or num_subaddresses > 1)
        if self.need_additional_txkeys:
            for _ in range(len(tsx_data.outputs)):
                self.additional_tx_keys.append(crypto.random_scalar())

        # Extra processing, payment id
        self.tx.version = 2
        self.tx.unlock_time = tsx_data.unlock_time
        await self.process_payment_id()
        await self.compute_hmac_keys(tsx_ctr)

    async def process_payment_id(self):
        """
        Payment id -> extra
        :return:
        """
        if self.tsx_data.payment_id is None or len(self.tsx_data.payment_id) == 0:
            return

        change_addr = self.tsx_data.change_dts.addr if self.tsx_data.change_dts else None
        view_key_pub_enc = monero.get_destination_view_key_pub(self.tsx_data.outputs, change_addr)
        if view_key_pub_enc == crypto.NULL_KEY_ENC:
            raise ValueError('Destinations have to have exactly one output to support encrypted payment ids')

        view_key_pub = crypto.decodepoint(view_key_pub_enc)
        payment_id_encr = monero.encrypt_payment_id(self.tsx_data.payment_id, view_key_pub, self.r)

        extra_nonce = monero.set_encrypted_payment_id_to_tx_extra_nonce(payment_id_encr)
        self.tx.extra = monero.add_extra_nonce_to_tx_extra([], extra_nonce)

    async def compute_hmac_keys(self, tsx_ctr):
        """
        Generate master key H(TsxData || r || c_tsx)
        :return:
        """
        writer = common.get_keccak_writer()
        ar1 = xmrserialize.Archive(writer, True)
        await ar1.message(self.tsx_data)
        await xmrserialize.dump_uvarint(writer, self.r)
        await xmrserialize.dump_uvarint(writer, tsx_ctr)
        self.key_master = writer.get_digest()
        self.key_hmac = common.keccak_hash(b'hmac' + self.key_master)

    def precompute_subaddr(self, account, indices):
        """
        Precomputes subaddresses for account (major) and list of indices (minors)
        Subaddresses have to be stored in encoded form - unique representation.
        Single point can have multiple extended coordinates representation - would not match during subaddress search.
        :param account:
        :param indices:
        :return:
        """
        self.state.precomp()
        for idx in indices:
            if account == 0 and idx == 0:
                self.subaddresses[crypto.encodepoint(self.trezor.creds.spend_key_public)] = (0, 0)
                continue

            pub = monero.get_subaddress_spend_public_key(self.trezor.creds.view_key_private,
                                                         self.trezor.creds.spend_key_public,
                                                         major=account, minor=idx)
            pub = crypto.encodepoint(pub)
            self.subaddresses[pub] = (account, idx)

    def in_memory(self):
        """
        Returns true if the input transaction can be processed whole in-memory
        :return:
        """
        return self.input_count == 0  # TODO: temporary, all tsx are not in-memory

    def inv_input_permutation(self, new_idx):
        """
        Finds inverse of the input permutation O(N)
        :param new_idx:
        :return:
        """
        for i in range(len(self.source_permutation)):
            if self.source_permutation[i] == new_idx:
                return i
        raise ValueError('Invalid index / permutation')

    def hmac_key_txin(self, idx):
        """
        Input hmac key
        :param idx:
        :return:
        """
        return common.keccak_hash(self.key_hmac + b'txin' + xmrserialize.dump_uvarint_b(idx))

    def hmac_key_txout(self, idx):
        """
        Output hmac key
        :param idx:
        :return:
        """
        return common.keccak_hash(self.key_hmac + b'txout' + xmrserialize.dump_uvarint_b(idx))

    async def set_input_cnt(self, inpt_cnt):
        """
        Sets input count
        :param inpt_cnt:
        :return:
        """
        self.state.inp_cnt(inpt_cnt > 1)
        self.input_count = inpt_cnt
        self.use_simple_rct = inpt_cnt > 1

    async def set_input(self, src_entr):
        """
        :param src_entr:
        :type src_entr: xmrtypes.TxSourceEntry
        :return:
        """
        self.state.input()
        self.inp_idx += 1
        if src_entr.real_output >= len(src_entr.outputs):
            raise ValueError('real_output index %s bigger than output_keys.size()' % (src_entr.real_output, len(src_entr.outputs)))
        self.summary_inputs_money += src_entr.amount

        out_key = crypto.decodepoint(src_entr.outputs[src_entr.real_output][1].dest)
        tx_key = crypto.decodepoint(src_entr.real_out_tx_key)
        additional_keys = [crypto.decodepoint(x) for x in src_entr.real_out_additional_tx_keys]

        secs = monero.generate_key_image_helper(self.trezor.creds, self.subaddresses, out_key,
                                                tx_key,
                                                additional_keys,
                                                src_entr.real_output_in_tx_index)
        xi, ki, di = secs
        self.input_secrets.append((xi, ))
        self.input_rcts.append(src_entr.rct)

        # Construct tx.vin
        vini = xmrtypes.TxinToKey(amount=src_entr.amount, k_image=crypto.encodepoint(ki))
        vini.key_offsets = [x[0] for x in src_entr.outputs]
        vini.key_offsets = monero.absolute_output_offsets_to_relative(vini.key_offsets)

        if src_entr.rct:
            vini.amount = 0

        if self.in_memory():
            self.tx.vin.append(vini)

        # HMAC(T_in,i || vin_i)
        kwriter = common.get_keccak_writer()
        ar = xmrserialize.Archive(kwriter, True)
        await ar.message(src_entr, xmrtypes.TxSourceEntry)
        await ar.message(vini, xmrtypes.TxinToKey)

        hmac_key_vini = self.hmac_key_txin(self.inp_idx)
        hmac_vini = common.compute_hmac(hmac_key_vini, kwriter.get_digest())

        return vini, hmac_vini

    async def tsx_inputs_done_inm(self):
        """
        In-memory post processing
        :return:
        """
        # Sort tx.in by key image
        self.source_permutation = list(range(self.inp_idx + 1))
        self.source_permutation.sort(key=lambda x: self.tx.vin[x].k_image)

        def swapper(x, y):
            self.tx.vin[x], self.tx.vin[y] = self.tx.vin[y], self.tx.vin[x]
            self.input_secrets[x], self.input_secrets[y] = self.input_secrets[y], self.input_secrets[x]
            self.input_rcts[x], self.input_rcts[y] = self.input_rcts[y], self.input_rcts[x]

        common.apply_permutation(self.source_permutation, swapper)

    async def tsx_inputs_done(self):
        """
        All inputs set
        :return:
        """
        self.state.input_done()
        if self.input_count != self.inp_idx + 1:
            raise ValueError('Input count mismatch')
        if self.in_memory():
            return await self.tsx_inputs_done_inm()

        # Iterative message hash computation
        self.tx_prefix_hasher.ar.message_field(self.tx, xmrtypes.TransactionPrefix.FIELDS[0])
        self.tx_prefix_hasher.ar.message_field(self.tx, xmrtypes.TransactionPrefix.FIELDS[1])

        # vins size
        self.tx_prefix_hasher.ar.container_size(self.input_count, xmrtypes.TransactionPrefix.FIELDS[2][1])
        return self.r_pub

    async def tsx_inputs_permutation(self, permutation):
        """
        Set sort permutation on the inputs - sorted by key image
        :param permutation:
        :return:
        """
        self.state.input_permutation()
        self.source_permutation = permutation

        def swapper(x, y):
            self.input_secrets[x], self.input_secrets[y] = self.input_secrets[y], self.input_secrets[x]
            self.input_rcts[x], self.input_rcts[y] = self.input_rcts[y], self.input_rcts[x]

        common.apply_permutation(self.source_permutation, swapper)
        self.inp_idx = -1

    async def tsx_input_vini(self, src_entr, vini, hmac):
        """
        Set Vini for message computation
        :param vini:
        :param hmac:
        :return:
        """
        self.state.input_vins()
        self.inp_idx += 1

        # HMAC(T_in,i || vin_i)
        kwriter = common.get_keccak_writer()
        ar = xmrserialize.Archive(kwriter, True)
        await ar.message(src_entr, xmrtypes.TxSourceEntry)
        await ar.message(vini, xmrtypes.TxinToKey)

        hmac_key_vini = self.hmac_key_txin(self.inv_input_permutation(self.inp_idx))
        hmac_vini = common.compute_hmac(hmac_key_vini, kwriter.get_digest())
        if not common.ct_equal(hmac_vini, hmac):
            raise ValueError('HMAC is not correct')

        # Serialize particular input type
        # Zero-out value during hashing
        if self.input_rcts[self.inp_idx]:
            vini.amount = 0
        self.tx_prefix_hasher.ar.field(vini, xmrtypes.TxInV)

    async def tsx_input_vini_done(self, src_entr, vini, hmac):
        """
        vini set
        :param src_entr:
        :param vini:
        :param hmac:
        :return:
        """
        self.state.input_vins_done()
        if self.inp_idx + 1 != self.input_count:
            raise ValueError('Invalid number of inputs')

    async def set_out1(self, dst_entr):
        """
        Set destination entry
        :param src_entr
        :type src_entr: xmrtypes.TxDestinationEntry
        :return:
        """
        self.state.set_output()
        self.out_idx += 1
        change_addr = self.tsx_data.change_dts.addr if self.tsx_data.change_dts else None

        if dst_entr.amount <= 0 and self.tx.version <= 1:
            raise ValueError('Destination with wrong amount: %s' % dst_entr.amount)

        if self.need_additional_txkeys:
            if dst_entr.is_subaddress:
                additional_txkey = crypto.ge_scalarmult(self.additional_tx_keys[self.out_idx],
                                                        crypto.decodepoint(dst_entr.addr.m_spend_public_key))
            else:
                additional_txkey = crypto.ge_scalarmult_base(self.additional_tx_keys[self.out_idx])

            self.additional_tx_public_keys.append(additional_txkey)

        if change_addr and dst_entr.addr == change_addr:
            # sending change to yourself; derivation = a*R
            derivation = monero.generate_key_derivation(self.r_pub, self.creds.view_key_private)

        else:
            # sending to the recipient; derivation = r*A (or s*C in the subaddress scheme)
            deriv_priv = self.additional_tx_keys[self.out_idx] if dst_entr.is_subaddress and self.need_additional_txkeys else self.r
            derivation = monero.generate_key_derivation(crypto.decodepoint(dst_entr.addr.m_view_public_key), deriv_priv)

        amount_key = crypto.derivation_to_scalar(derivation, self.out_idx)
        tx_out_key = crypto.derive_public_key(derivation, self.out_idx, crypto.decodepoint(dst_entr.addr.m_spend_public_key))
        tk = xmrtypes.TxoutToKey(key=crypto.encodepoint(tx_out_key))
        tx_out = xmrtypes.TxOut(amount=dst_entr.amount, target=tk)
        self.tx.vout.append(tx_out)
        self.summary_outs_money += dst_entr.amount

        self.output_secrets.append((amount_key, ))
        self.output_amounts.append(dst_entr.amount)

        # Hmac dest_entr
        kwriter = common.get_keccak_writer()
        ar = xmrserialize.Archive(kwriter, True)
        await ar.message(dst_entr, xmrtypes.TxDestinationEntry)
        await ar.message(tx_out, xmrtypes.TxOut)

        hmac_key_vouti = self.hmac_key_txout(self.out_idx)
        hmac_vouti = common.compute_hmac(hmac_key_vouti, kwriter.get_digest())
        return tx_out, hmac_vouti

    async def all_out1_set(self):
        """
        All out1 set phase
        Adds additional public keys to the tx.extra
        :return:
        """
        self.state.set_output()
        if self.out_idx + 1 != len(self.tsx_data.outputs):
            raise ValueError('Invalid out num')

        # Set public key to the extra
        # Not needed to remove - extra is clean
        # self.tx.extra = await monero.remove_field_from_tx_extra(self.tx.extra, xmrtypes.TxExtraPubKey)
        monero.add_tx_pub_key_to_extra(self.tx.extra, self.r_pub)

        # Not needed to remove - extra is clean
        # self.tx.extra = await monero.remove_field_from_tx_extra(self.tx.extra, xmrtypes.TxExtraAdditionalPubKeys)
        if self.need_additional_txkeys:
            await monero.add_additional_tx_pub_keys_to_extra(self.tx.extra, self.additional_tx_public_keys)

        if self.summary_outs_money > self.summary_inputs_money:
            raise ValueError('Transaction inputs money (%s) less than outputs money (%s)'
                             % (self.summary_inputs_money, self.summary_outs_money))

        # vout hash, zero-out amount
        for out in self.tx.vout:
            out.amount = 0

        if self.in_memory():
            self.tx_prefix_hasher.ar.message_field(self.tx, xmrtypes.TransactionPrefix.FIELDS[0])
            self.tx_prefix_hasher.ar.message_field(self.tx, xmrtypes.TransactionPrefix.FIELDS[1])
            self.tx_prefix_hasher.ar.message_field(self.tx, xmrtypes.TransactionPrefix.FIELDS[2])
        self.tx_prefix_hasher.ar.message_field(self.tx, xmrtypes.TransactionPrefix.FIELDS[3])
        self.tx_prefix_hasher.ar.message_field(self.tx, xmrtypes.TransactionPrefix.FIELDS[4])
        self.tx_prefix_hash = self.tx_prefix_hasher.kwriter.get_digest()

    async def signature(self, tx):
        """
        Computes the signature
        TODO: implement according to the protocol

        :param tx: const data
        :type tx: xmrtypes.TxConstructionData
        :return:
        """
        amount_in = 0
        inamounts = [None] * len(self.source_permutation)
        index = [None] * len(self.source_permutation)
        in_sk = [None] * len(self.source_permutation)  # type: list[xmrtypes.CtKey]

        # TODO: iterative?
        for i in range(len(self.source_permutation)):
            idx = self.source_permutation[i]
            src = tx.sources[idx]
            amount_in += src.amount
            inamounts[i] = src.amount
            index[i] = src.real_output
            in_sk[i] = xmrtypes.CtKey(dest=self.input_secrets[i][0], mask=crypto.decodeint(src.mask))
            # TODO: kLRki

            # private key correctness test
            if __debug__:
                assert crypto.point_eq(crypto.decodepoint(src.outputs[src.real_output][1].dest),
                                       crypto.scalarmult_base(in_sk[i].dest))
                assert crypto.point_eq(crypto.decodepoint(src.outputs[src.real_output][1].mask),
                                       crypto.gen_c(in_sk[i].mask, inamounts[i]))

        # TODO: iterative?
        destinations = []
        outamounts = []
        amount_out = 0
        for idx, dst in enumerate(tx.dests):
            destinations.append(crypto.decodepoint(self.tx.vout[idx].target.key))
            outamounts.append(self.tx.vout[idx].amount)
            amount_out += self.tx.vout[idx].amount

        if self.use_simple_rct:
            mix_ring = [None] * (self.inp_idx + 1)
            for i in range(len(self.source_permutation)):
                src = tx.sources[self.source_permutation[i]]
                mix_ring[i] = []
                for idx2, out in enumerate(src.outputs):
                    mix_ring[i].append(out[1])

        else:
            n_total_outs = len(tx.sources[0].outputs)
            mix_ring = [None] * n_total_outs
            for idx in range(n_total_outs):
                mix_ring[idx] = []
                for i in range(len(self.source_permutation)):
                    src = tx.sources[self.source_permutation[i]]
                    mix_ring[idx].append(src.outputs[idx][1])

        if not self.use_simple_rct and amount_in > amount_out:
            outamounts.append(amount_in - amount_out)

        # Hide amounts
        self.zero_out_amounts()

        # Tx prefix hash
        await self.compute_tx_prefix_hash()

        # Signature
        if self.use_simple_rct:
            rv = await self.gen_rct_simple(in_sk, destinations, inamounts, outamounts, amount_in - amount_out, mix_ring, None, None, index)
        else:
            rv = await self.gen_rct(in_sk, destinations, outamounts, mix_ring, None, None, tx.sources[0].real_output)

        # Recode for serialization
        rv = monero.recode_rct(rv, encode=True)
        self.tx.signatures = []
        self.tx.rct_signatures = rv
        del rv

        # Serialize response
        writer = xmrserialize.MemoryReaderWriter()
        ar1 = xmrserialize.Archive(writer, True)
        await ar1.message(self.tx, msg_type=xmrtypes.Transaction)

        return bytes(writer.buffer)

    def zero_out_amounts(self):
        """
        Zero out all amounts to mask rct outputs, real amounts are now encrypted
        :return:
        """
        for idx, inx in enumerate(self.tx.vin):
            if self.input_rcts[idx]:
                inx.amount = 0

        for out in self.tx.vout:
            out.amount = 0

    async def compute_tx_prefix_hash(self):
        """
        Computes tx prefix hash
        :return:
        """
        self.tx_prefix_hash = await monero.get_transaction_prefix_hash(self.tx)
        return self.tx_prefix_hash

    async def gen_rct_header(self, destinations, outamounts):
        """
        Initializes RV RctSig structure, processes outputs, computes range proofs, ecdh info masking.
        Common to gen_rct and gen_rct_simple.

        :param destinations:
        :param outamounts:
        :return:
        """
        rv = xmrtypes.RctSig()
        rv.p = xmrtypes.RctSigPrunable()

        rv.message = self.tx_prefix_hash
        rv.outPk = [None] * len(destinations)

        if self.use_bulletproof:
            rv.p.bulletproofs = [None] * len(destinations)
        else:
            rv.p.rangeSigs = [None] * len(destinations)
        rv.ecdhInfo = [None] * len(destinations)

        # Output processing
        sumout = 0
        out_sk = [None] * len(destinations)
        for idx in range(len(destinations)):
            rv.outPk[idx] = xmrtypes.CtKey(dest=crypto.encodepoint(destinations[idx]))
            C, mask, rsig = None, 0, None

            # Rangeproof
            if self.use_bulletproof:
                raise ValueError('Bulletproof not yet supported')

            else:
                C, mask, rsig = ring_ct.prove_range(outamounts[idx])
                rv.p.rangeSigs[idx] = rsig
                if __debug__:
                    assert ring_ct.ver_range(C, rsig)
                    assert crypto.point_eq(C, crypto.point_add(
                        crypto.scalarmult_base(mask),
                        crypto.scalarmult_h(outamounts[idx])))

                # Recoding to structure
                monero.recode_rangesig(rsig, encode=True)

            # Mask sum
            rv.outPk[idx].mask = crypto.encodepoint(C)
            sumout = crypto.sc_add(sumout, mask)
            out_sk[idx] = xmrtypes.CtKey(mask=mask)

            # ECDH masking
            amount_key = crypto.encodeint(self.output_secrets[idx][0])
            rv.ecdhInfo[idx] = xmrtypes.EcdhTuple(mask=mask, amount=outamounts[idx])
            rv.ecdhInfo[idx] = ring_ct.ecdh_encode(rv.ecdhInfo[idx], derivation=amount_key)
            monero.recode_ecdh(rv.ecdhInfo[idx], encode=True)

        return rv, sumout, out_sk

    async def gen_rct(self, in_sk, destinations, amounts, mix_ring, kLRki, msout, index):
        """
        Full ring CT signature.
        Used when there is only one input transaction to spend.

        :param in_sk:
        :param destinations:
        :param amounts:
        :param mix_ring:
        :param kLRki:
        :param msout:
        :param index:
        :param out_sk:
        :return:
        """
        if len(amounts) != len(destinations) and len(amounts) != len(destinations) + 1:
            raise ValueError('Different number of amounts/destinations')
        if len(self.output_secrets) != len(destinations):
            raise ValueError('Different number of amount_keys/destinations')
        if index >= len(mix_ring):
            raise ValueError('Bad index into mix ring')
        for n in range(len(mix_ring)):
            if len(mix_ring[n]) != len(in_sk):
                raise ValueError('Bad mixring size')
        if (not kLRki or not msout) and (kLRki or msout):
            raise ValueError('Only one of kLRki/mscout is present')

        rv, sumout, out_sk = await self.gen_rct_header(destinations, amounts)
        rv.type = xmrtypes.RctType.FullBulletproof if self.use_bulletproof else xmrtypes.RctType.Full

        if len(amounts) > len(destinations):
            rv.txnFee = amounts[len(destinations)]
        else:
            rv.txnFee = 0

        txn_fee_key = crypto.scalarmult_h(rv.txnFee)
        rv.mixRing = mix_ring
        # TODO: msout multisig

        full_message = await monero.get_pre_mlsag_hash(rv)
        rv.p.MGs = [
            mlsag2.prove_rct_mg(full_message,
                                rv.mixRing,
                                in_sk, out_sk, rv.outPk, kLRki, None, index, txn_fee_key)
        ]

        if __debug__:
            assert mlsag2.ver_rct_mg(rv.p.MGs[0], rv.mixRing, rv.outPk, txn_fee_key, full_message)
        return rv

    async def gen_rct_simple(self, in_sk, destinations, inamounts, outamounts, txn_fee, mix_ring, kLRki, msout, index):
        """
        Generate simple RCT signature.

        :param in_sk:
        :param destinations:
        :param inamounts:
        :param outamounts:
        :param txn_fee:
        :param mix_ring:
        :param kLRki:
        :param msout:
        :param index:
        :param out_sk:
        :return:
        """
        if len(inamounts) == 0:
            raise ValueError("Empty inamounts")
        if len(inamounts) != len(in_sk):
            raise ValueError("Different number of inamounts/inSk")
        if len(outamounts) != len(destinations):
            raise ValueError("Different number of amounts/destinations")
        if len(self.output_secrets) != len(destinations):
            raise ValueError("Different number of amount_keys/destinations")
        if len(index) != len(in_sk):
            raise ValueError("Different number of index/inSk")
        if len(mix_ring) != len(in_sk):
            raise ValueError("Different number of mixRing/inSk")
        for idx in range(len(mix_ring)):
            if index[idx] >= len(mix_ring[idx]):
                raise ValueError('Bad index into mixRing')

        rv, sumout, out_sk = await self.gen_rct_header(destinations, outamounts)
        rv.type = xmrtypes.RctType.SimpleBulletproof if self.use_bulletproof else xmrtypes.RctType.Simple
        rv.txnFee = txn_fee
        rv.mixRing = mix_ring

        # Pseudooutputs
        pseudo_outs = [None] * len(inamounts)
        rv.p.MGs = [None] * len(inamounts)
        sumpouts = 0
        a = []
        for idx in range(len(inamounts)-1):
            a.append(crypto.random_scalar())
            sumpouts = crypto.sc_add(sumpouts, a[idx])
            pseudo_outs[idx] = crypto.gen_c(a[idx], inamounts[idx])

        a.append(crypto.sc_sub(sumout, sumpouts))
        pseudo_outs[-1] = crypto.gen_c(a[-1], inamounts[-1])

        if self.use_bulletproof:
            rv.p.pseudoOuts = [crypto.encodepoint(x) for x in pseudo_outs]
        else:
            rv.pseudoOuts = [crypto.encodepoint(x) for x in pseudo_outs]

        full_message = await monero.get_pre_mlsag_hash(rv)

        # TODO: msout multisig
        for i in range(len(inamounts)):
            rv.p.MGs[i] = mlsag2.prove_rct_mg_simple(
                full_message,
                rv.mixRing[i],
                in_sk[i], a[i],
                pseudo_outs[i],
                kLRki[i] if kLRki else None, None, index[i])

            if __debug__:
                assert mlsag2.ver_rct_mg_simple(full_message, rv.p.MGs[i], rv.mixRing[i], pseudo_outs[i])

        return rv


