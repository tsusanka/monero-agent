#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Dusan Klinec, ph4r05, 2018


import os
from trezorlib import coins
from trezorlib import tx_api
from trezorlib.client import TrezorClientDebugLink
from trezorlib.transport import get_transport

mnemonic12 = 'alcohol woman abuse must during monitor noble actual mixed trade anger aisle'

path = os.environ.get('TREZOR_PATH', 'udp:127.0.0.1:21324')
wirelink = get_transport(path)
debuglink = wirelink.find_debug()
client = TrezorClientDebugLink(wirelink)
client.set_debuglink(debuglink)
client.transport.session_begin()

client.wipe_device()
client.load_device_by_mnemonic(mnemonic=mnemonic12, pin='', passphrase_protection=False, label='ph4test', language='english')

client.transport.session_end()
client.close()

