#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison,wrong-import-position,too-many-nested-blocks

import os
import sys
import hashlib
import datetime

from flask import g

from lvfs import app, db, ploader

from lvfs.analytics.utils import _generate_stats_for_datestr
from lvfs.firmware.utils import _purge_old_deleted_firmware
from lvfs.firmware.utils import _sign_firmware_all, _delete_embargo_obsoleted_fw
from lvfs.main.utils import _regenerate_metrics
from lvfs.metadata.utils import _regenerate_and_sign_metadata
from lvfs.models import Component, Category, Protocol, Firmware, User
from lvfs.models import _get_datestr_from_datetime
from lvfs.queries.utils import _query_run_all
from lvfs.reports.utils import _regenerate_reports
from lvfs.shards.utils import _regenerate_shard_infos
from lvfs.tests.utils import _test_run_all
from lvfs.upload.uploadedfile import UploadedFile, MetadataInvalid
from lvfs.users.utils import _user_disable_notify, _user_disable_actual
from lvfs.util import _get_absolute_path

def _repair_ts():

    # fix any timestamps that are incorrect
    for md in db.session.query(Component).filter(Component.release_timestamp < 1980):
        fn = _get_absolute_path(md.fw)
        if not os.path.exists(fn):
            continue
        print(fn, md.release_timestamp)
        try:
            ufile = UploadedFile(is_strict=False)
            for cat in db.session.query(Category):
                ufile.category_map[cat.value] = cat.category_id
            for pro in db.session.query(Protocol):
                ufile.protocol_map[pro.value] = pro.protocol_id
            with open(fn, 'rb') as f:
                ufile.parse(os.path.basename(fn), f.read())
        except MetadataInvalid as e:
            print('failed to parse file: {}'.format(str(e)))
            continue
        for md_local in ufile.fw.mds:
            if md_local.appstream_id == md.appstream_id:
                print('repairing timestamp from {} to {}'.format(md.release_timestamp,
                                                                 md_local.release_timestamp))
                md.release_timestamp = md_local.release_timestamp
                md.fw.mark_dirty()

    # all done
    db.session.commit()

def _fsck():
    for firmware_id, in db.session.query(Firmware.firmware_id)\
                                  .order_by(Firmware.firmware_id.asc()):
        fw = db.session.query(Firmware)\
                       .filter(Firmware.firmware_id == firmware_id)\
                       .one()
        fn = _get_absolute_path(fw)
        if not os.path.isfile(fn):
            print('firmware {} is missing, expected {}'.format(fw.firmware_id, fn))

def _repair_csum():

    # fix all the checksums and file sizes
    for firmware_id, in db.session.query(Firmware.firmware_id)\
                                  .order_by(Firmware.firmware_id.asc()):
        fw = db.session.query(Firmware)\
                       .filter(Firmware.firmware_id == firmware_id)\
                       .one()
        try:
            print('checking {}'.format(fw.filename_absolute))
            with open(fw.filename_absolute, 'rb') as f:
                checksum_signed_sha1 = hashlib.sha1(f.read()).hexdigest()
                if checksum_signed_sha1 != fw.checksum_signed_sha1:
                    print('repairing checksum from {} to {}'.format(fw.checksum_signed_sha1,
                                                                    checksum_signed_sha1))
                    fw.checksum_signed_sha1 = checksum_signed_sha1
                    fw.mark_dirty()
                checksum_signed_sha256 = hashlib.sha256(f.read()).hexdigest()
                if checksum_signed_sha256 != fw.checksum_signed_sha256:
                    print('repairing checksum from {} to {}'.format(fw.checksum_signed_sha256,
                                                                    checksum_signed_sha256))
                    fw.checksum_signed_sha256 = checksum_signed_sha256
                    fw.mark_dirty()
            for md in fw.mds:
                sz = os.path.getsize(fw.filename_absolute)
                if sz != md.release_download_size:
                    print('repairing size from {} to {}'.format(md.release_download_size, sz))
                    md.release_download_size = sz
                    md.fw.mark_dirty()
        except FileNotFoundError as _:
            pass

    # all done
    db.session.commit()

def _ensure_tests():

    # ensure the test has been added for the firmware type
    for firmware_id, in db.session.query(Firmware.firmware_id)\
                                  .order_by(Firmware.timestamp):
        fw = db.session.query(Firmware)\
                       .filter(Firmware.firmware_id == firmware_id)\
                       .one()
        if not fw.is_deleted:
            ploader.ensure_test_for_fw(fw)
            db.session.commit()

def _main_with_app_context():
    if 'repair-ts' in sys.argv:
        _repair_ts()
    if 'repair-csum' in sys.argv:
        _repair_csum()
    if 'fsck' in sys.argv:
        _fsck()
    if 'ensure' in sys.argv:
        _ensure_tests()
    if 'firmware' in sys.argv:
        _sign_firmware_all()
    if 'metadata' in sys.argv:
        _regenerate_and_sign_metadata()
    if 'metadata-embargo' in sys.argv:
        _regenerate_and_sign_metadata(only_embargo=True)
    if 'purgedelete' in sys.argv:
        _delete_embargo_obsoleted_fw()
        _purge_old_deleted_firmware()
    if 'fwchecks' in sys.argv:
        _test_run_all()
        _query_run_all()
        _user_disable_notify()
        _user_disable_actual()
    if 'stats' in sys.argv:
        val = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(days=1))
        _generate_stats_for_datestr(val)
        _regenerate_metrics()
        _regenerate_shard_infos()
        _regenerate_reports()
    if 'statsmigrate' in sys.argv:
        for days in range(1, 720):
            val = _get_datestr_from_datetime(datetime.date.today() - datetime.timedelta(days=days))
            _generate_stats_for_datestr(val)

if __name__ == '__main__':

    if len(sys.argv) < 2:
        print('Usage: %s [metadata] [firmware]' % sys.argv[0])
        sys.exit(1)
    try:
        with app.test_request_context():
            app.config['SERVER_NAME'] = app.config['HOST_NAME']
            g.user = db.session.query(User).filter(User.username == 'anon@fwupd.org').first()
            _main_with_app_context()
    except NotImplementedError as e:
        print(str(e))
        sys.exit(1)

    # success
    sys.exit(0)
