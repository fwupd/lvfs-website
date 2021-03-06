#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import base64
import os
import hashlib

from lvfs import app

def _addr_hash(value: str) -> str:
    """ Generate a salted hash of the IP address """
    salt = app.config['SECRET_ADDR_SALT']
    return hashlib.sha1((salt + value).encode('utf-8')).hexdigest()

def _otp_hash() -> str:
    """ Generate a random OTP secret """
    return base64.b32encode(os.urandom(10)).decode('utf-8')

def _is_sha1(text: str) -> bool:
    if len(text) != 40:
        return False
    try:
        _ = int(text, 16)
    except ValueError:
        return False
    return True

def _is_sha256(text: str) -> bool:
    if len(text) != 64:
        return False
    try:
        _ = int(text, 16)
    except ValueError:
        return False
    return True
