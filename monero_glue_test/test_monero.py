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

from mnero import mininero
import monero_serialize as xmrser
from monero_serialize import xmrserialize, xmrtypes
from monero_glue import trezor, monero, common, crypto, agent
from mnero import keccak2


class MoneroTest(aiounittest.AsyncTestCase):
    """Simple tests"""

    def __init__(self, *args, **kwargs):
        super(MoneroTest, self).__init__(*args, **kwargs)

    def test_derive_subaddress_public_key(self):
        out_key = crypto.decodepoint(bytes(
            [0xf4, 0xef, 0xc2, 0x9d, 0xa4, 0xcc, 0xd6, 0xbc, 0x6e, 0x81, 0xf5, 0x2a, 0x6f, 0x47, 0xb2, 0x95, 0x29, 0x66,
             0x44, 0x2a, 0x7e, 0xfb, 0x49, 0x90, 0x1c, 0xce, 0x06, 0xa7, 0xa3, 0xbe, 0xf3, 0xe5]))
        deriv = crypto.decodepoint(bytes(
            [0x25, 0x9e, 0xf2, 0xab, 0xa8, 0xfe, 0xb4, 0x73, 0xcf, 0x39, 0x05, 0x8a, 0x0f, 0xe3, 0x0b, 0x9f, 0xf6, 0xd2,
             0x45, 0xb4, 0x2b, 0x68, 0x26, 0x68, 0x7e, 0xbd, 0x6b, 0x63, 0x12, 0x8a, 0xff, 0x64]))
        res = crypto.encodepoint(monero.derive_subaddress_public_key(out_key, deriv, 5))
        self.assertEqual(res, bytes(
            [0x5a, 0x10, 0xcc, 0xa9, 0x00, 0xee, 0x47, 0xa7, 0xf4, 0x12, 0xcd, 0x66, 0x1b, 0x29, 0xf5, 0xab, 0x35, 0x6d,
             0x6a, 0x19, 0x51, 0x88, 0x45, 0x93, 0xbb, 0x17, 0x0b, 0x5e, 0xc8, 0xb6, 0xf2, 0xe8]))


if __name__ == "__main__":
    unittest.main()  # pragma: no cover


