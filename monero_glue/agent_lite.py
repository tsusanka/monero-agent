#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Dusan Klinec, ph4r05, 2018

import random
import base64
import unittest
import pkg_resources
import requests
import asyncio
import aiounittest
import binascii

import monero_serialize as xmrser
from monero_serialize import xmrserialize, xmrtypes
from monero_glue import trezor, trezor_lite, monero, common, crypto
from mnero import keccak2


class TData(object):
    """
    Agent transaction-scoped data
    """
    def __init__(self):
        self.tsx_data = None  # type: monero.TsxData
        self.tx = xmrtypes.Transaction(vin=[], vout=[], extra=[])
        self.tx_in_hmacs = []
        self.tx_out_hmacs = []
        self.source_permutation = []


class Agent(object):
    """
    Glue agent, running on host
    """
    def __init__(self, trezor):
        self.trezor = trezor  # type: trezor_lite.TrezorLite
        self.ct = None  # type: TData

    async def transfer_unsigned(self, unsig):
        txes = []
        for tx in unsig.txes:
            self.ct = TData()

            payment_id = []
            extras = await monero.parse_extra_fields(tx.extra)
            extra_nonce = monero.find_tx_extra_field_by_type(extras, xmrtypes.TxExtraNonce)
            if extra_nonce and monero.has_encrypted_payment_id(extra_nonce.nonce):
                payment_id = monero.get_encrypted_payment_id_from_tx_extra_nonce(extra_nonce.nonce)

            # Init transaction
            tsx_data = trezor.TsxData()
            tsx_data.version = 1
            tsx_data.payment_id = payment_id
            tsx_data.unlock_time = tx.unlock_time
            tsx_data.outputs = tx.dests
            tsx_data.change_dts = tx.change_dts

            self.ct.tsx_data = tsx_data
            await self.trezor.init_transaction(tsx_data)

            # Subaddresses
            await self.trezor.precompute_subaddr(tx.subaddr_account, tx.subaddr_indices)

            # Set transaction inputs
            await self.trezor.set_input_count(len(tx.sources))
            for idx, src in enumerate(tx.sources):
                vini, vini_hmac = await self.trezor.set_tsx_input(src)
                self.ct.tx.vin.append(vini)
                self.ct.tx_in_hmacs.append(vini_hmac)

            await self.trezor.tsx_inputs_done()

            # Sort key image
            self.ct.source_permutation = list(range(len(tx.sources)))
            self.ct.source_permutation.sort(key=lambda x: self.ct.tx.vin[x].k_image)

            def swapper(x, y):
                self.ct.tx.vin[x], self.ct.tx.vin[y] = self.ct.tx.vin[y], self.ct.tx.vin[x]
                tx.sources[x], tx.sources[y] = tx.sources[y], tx.sources[x]

            common.apply_permutation(self.ct.source_permutation, swapper)
            await self.trezor.tsx_inputs_permutation(self.ct.source_permutation)

            # Set vin_i back
            for idx in range(len(self.ct.tx.vin)):
                self.trezor.tsx_input_vini(tx.sources[idx], self.ct.tx.vin[idx], self.ct.tx_in_hmacs[idx])

            for dst in tx.dests:
                vouti, vouti_mac = await self.trezor.set_tsx_output1(dst)
                self.ct.tx.vout.append(vouti)
                self.ct.tx_out_hmacs.append(vouti_mac)

            await self.trezor.all_out1_set()


            # Unfinished proto
            buf = await self.trezor.tsx_obj.signature(tx)
            txes.append(buf)
        return txes

