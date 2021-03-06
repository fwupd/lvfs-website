#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,no-member,too-few-public-methods

import os
import glob
from typing import Dict, List

import yara

from lvfs import db
from lvfs.pluginloader import PluginBase, PluginError
from lvfs.pluginloader import PluginSettingBool, PluginSettingTextList
from lvfs.tests.models import Test
from lvfs.claims.models import Claim
from lvfs.components.models import Component

def _run_on_blob(self, test: Test, md: Component, title: str, blob: bytes) -> None:
    matches = self.rules.match(data=blob)
    for match in matches:

        # do what we can
        description = None
        if 'description' in match.meta:
            description = match.meta['description'].replace('\0', '')

        if 'fail' not in match.meta or match.meta['fail']:
            msg = '{} YARA test failed'.format(match.rule)
            for string in match.strings:
                if len(string) == 3:
                    try:
                        msg += ': found {}'.format(string[2].decode())
                    except UnicodeDecodeError as _:
                        pass
            if description:
                msg += ': {}'.format(description)
            test.add_fail(title, msg)
        elif 'claim' in match.meta:
            claim = db.session.query(Claim)\
                              .filter(Claim.kind == match.meta['claim'])\
                              .first()
            if not claim:
                test.add_fail('YARA', 'Failed to find claim: {}'.format(match.meta['claim']))
                continue
            md.add_claim(claim)

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)
        self.rules = None
        self.name = 'Blocklist'
        self.summary = 'Use YARA to check firmware for problems'
        self.order_after = ['uefi-extract', 'intelme']

    def settings(self):
        s = []
        s.append(PluginSettingBool('blocklist_enabled', 'Enabled', True))
        s.append(PluginSettingTextList('blocklist_dirs', 'Rule Directories',
                                       ['plugins/blocklist/rules']))
        return s

    def ensure_test_for_fw(self, fw):

        # add if not already exists
        test = fw.find_test_by_plugin_id(self.id)
        if not test:
            test = Test(plugin_id=self.id, waivable=True)
            fw.tests.append(test)

    def run_test_on_md(self, test, md):

        # compile the list of rules
        if not self.rules:
            fns: List[str] = []
            for value in self.get_setting('blocklist_dirs', required=True).split(','):
                fns.extend(glob.glob(os.path.join(value, '*.yar')))
            if not fns:
                test.add_pass('No YARA rules to use')
                return
            filepaths: Dict[str, str] = {}
            for fn in fns:
                filepaths[os.path.basename(fn)] = fn
            try:
                self.rules = yara.compile(filepaths=filepaths)
            except yara.SyntaxError as e:
                test.add_fail('YARA', 'Failed to compile rules: {}'.format(str(e)))
                return

        # run analysis on the component and any shards
        if md.blob:
            _run_on_blob(self, test, md, md.filename_contents, md.blob)
        for shard in md.shards:
            if shard.blob:
                _run_on_blob(self, test, md, shard.name, shard.blob)

# run with PYTHONPATH=. ./env/bin/python3 plugins/blocklist/__init__.py
if __name__ == '__main__':
    import sys
    from lvfs.firmware.models import Firmware

    plugin = Plugin()
    _test = Test(plugin_id=plugin.id)
    _fw = Firmware()
    _md = Component()
    _md.blob = b'CN=DO NOT TRUST - AMI Test PK'
    _fw.mds.append(_md)
    plugin.run_test_on_md(_test, _md)
    for attribute in _test.attributes:
        print(attribute)
