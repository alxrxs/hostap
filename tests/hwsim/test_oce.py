# OCE tests
# Copyright (c) 2016, Intel Deutschland GmbH
#
# This software may be distributed under the terms of the BSD license.
# See README for more details.

import logging
logger = logging.getLogger()

import hostapd
from wpasupplicant import WpaSupplicant

from hwsim_utils import set_rx_rssi, reset_rx_rssi
import time
import binascii
import struct
import os
from datetime import datetime
from utils import HwsimSkip
from tshark import run_tshark

def check_set_tx_power(dev, apdev):
    hapd = hostapd.add_ap(apdev[0], {'ssid': 'check_tx_power'})
    set_rx_rssi(hapd, -50)

    dev[0].scan(freq=2412)
    ev = dev[0].wait_event(["CTRL-EVENT-SCAN-RESULTS"], 2)

    res = dev[0].request("SCAN_RESULTS")
    if '-50' not in res:
        raise HwsimSkip('set_rx_rssi not supported')

    reset_rx_rssi(hapd)

    dev[0].scan(freq=2412)
    ev = dev[0].wait_event(["CTRL-EVENT-SCAN-RESULTS"], 2)

    res = dev[0].request("SCAN_RESULTS")
    if '-30' not in res:
        raise HwsimSkip('set_rx_rssi not supported')

def run_rssi_based_assoc_rej_timeout(dev, apdev, params):
    rssi_retry_to = 5

    ap_params = {'ssid': "test-RSSI-ar-to",
                 'rssi_reject_assoc_rssi': '-45',
                 'rssi_reject_assoc_timeout': str(rssi_retry_to)}

    logger.info("Set APs RSSI rejection threshold to -45 dBm, retry timeout: " +
                str(rssi_retry_to))
    hapd = hostapd.add_ap(apdev[0], ap_params)

    logger.info("Set STAs TX RSSI to -50")
    set_rx_rssi(dev[0], -50)

    logger.info("STA is trying to connect")
    dev[0].connect("test-RSSI-ar-to", key_mgmt="NONE", scan_freq="2412",
                   wait_connect=False)

    ev = dev[0].wait_event(['CTRL-EVENT-ASSOC-REJECT'], 2)
    if ev is None:
        raise Exception("Association not rejected")
    if 'status_code=34' not in ev:
        raise Exception("STA assoc request was not rejected with status code 34: " + ev)
    t_rej = datetime.now()

    # Set the scan interval to make dev[0] look for connections
    if 'OK' not in dev[0].request("SCAN_INTERVAL 1"):
        raise Exception("Failed to set scan interval")

    logger.info("Validate that STA did not connect or sent assoc request within retry timeout")
    ev = dev[0].wait_event(['CTRL-EVENT-CONNECTED', 'CTRL-EVENT-ASSOC-REJECT'],
                           rssi_retry_to + 2)
    t_ev = datetime.now()

    if ((t_ev - t_rej).total_seconds() < rssi_retry_to):
        raise Exception("STA sent assoc request within retry timeout")

    if 'CTRL-EVENT-CONNECTED' in ev:
        raise Exception("STA connected with low RSSI")

    if not ev:
        raise Exception("STA didn't send association request after retry timeout!")

def test_rssi_based_assoc_rej_timeout(dev, apdev, params):
    """RSSI-based association rejection: no assoc request during retry timeout"""
    check_set_tx_power(dev, apdev)
    try:
        run_rssi_based_assoc_rej_timeout(dev, apdev, params)
    finally:
        reset_rx_rssi(dev[0])
        dev[0].request("SCAN_INTERVAL 5")

def run_rssi_based_assoc_rej_good_rssi(dev, apdev):
    ap_params = {'ssid': "test-RSSI-ar-to",
                 'rssi_reject_assoc_rssi': '-45',
                 'rssi_reject_assoc_timeout': '60'}

    logger.info("Set APs RSSI rejection threshold to -45 dBm")
    hapd = hostapd.add_ap(apdev[0], ap_params)

    logger.info("Set STAs TX RSSI to -45")
    set_rx_rssi(dev[0], -45)

    logger.info("STA is trying to connect")
    dev[0].connect("test-RSSI-ar-to", key_mgmt="NONE", scan_freq="2412")

def test_rssi_based_assoc_rej_good_rssi(dev, apdev):
    """RSSI-based association rejection: STA with RSSI above the threshold connects"""
    check_set_tx_power(dev, apdev)
    try:
        run_rssi_based_assoc_rej_good_rssi(dev, apdev)
    finally:
        reset_rx_rssi(dev[0])

def run_rssi_based_assoc_rssi_change(dev, hapd):
    logger.info("Set STAs and APs TX RSSI to -50")
    set_rx_rssi(dev[0], -50)
    set_rx_rssi(hapd, -50)

    # Set the scan interval to make dev[0] look for connections
    if 'OK' not in dev[0].request("SCAN_INTERVAL 1"):
        raise Exception("Failed to set scan interval")

    logger.info("STA is trying to connect")
    dev[0].connect("test-RSSI-ar-to", key_mgmt="NONE", scan_freq="2412",
                   wait_connect=False)

    try:
        dev[0].wait_completed(2)
    except:
        logger.info("STA didn't connect after 2 seconds.")
    else:
        raise Exception("STA connected with low RSSI")

    logger.info("Set STAs and APs TX RSSI to -40dBm, validate that STA connects")
    set_rx_rssi(dev[0], -40)
    set_rx_rssi(hapd, -40)

    dev[0].wait_completed(2)

def test_rssi_based_assoc_rssi_change(dev, apdev):
    """RSSI-based association rejection: connect after improving RSSI"""
    check_set_tx_power(dev, apdev)
    try:
        ap_params = {'ssid': "test-RSSI-ar-to",
                     'rssi_reject_assoc_rssi': '-45',
                     'rssi_reject_assoc_timeout': '60'}

        logger.info("Set APs RSSI rejection threshold to -45 dBm, retry timeout: 60")
        hapd = hostapd.add_ap(apdev[0], ap_params)

        run_rssi_based_assoc_rssi_change(dev, hapd)
    finally:
        reset_rx_rssi(dev[0])
        reset_rx_rssi(hapd)
        dev[0].request("SCAN_INTERVAL 5")

def test_oce_ap(dev, apdev):
    """OCE AP"""
    ssid = "test-oce"
    passphrase = 'qwertyuiop'
    params = hostapd.wpa2_params(ssid=ssid, passphrase=passphrase)
    params['ieee80211w'] = "1"
    params['mbo'] = "1"
    params['oce'] = "4"
    hapd = hostapd.add_ap(apdev[0], params)
    dev[0].connect(ssid, psk=passphrase, ieee80211w="1", scan_freq="2412")

def test_oce_ap_open(dev, apdev):
    """OCE AP (open)"""
    ssid = "test-oce"
    params = {"ssid": ssid}
    params['mbo'] = "1"
    params['oce'] = "4"
    hapd = hostapd.add_ap(apdev[0], params)
    dev[0].connect(ssid, key_mgmt="NONE", scan_freq="2412")

def test_oce_ap_open_connect_cmd(dev, apdev):
    """OCE AP (open, connect command)"""
    ssid = "test-oce"
    params = {"ssid": ssid}
    params['mbo'] = "1"
    params['oce'] = "4"
    hapd = hostapd.add_ap(apdev[0], params)
    wpas = WpaSupplicant(global_iface='/tmp/wpas-wlan5')
    wpas.interface_add("wlan5", drv_params="force_connect_cmd=1")
    wpas.connect(ssid, key_mgmt="NONE", scan_freq="2412")

def oce_probe_resp_da(dev, hapd, params, elems):
    """Scan with elements added to the Probe Request frames and return the
    destination addresses of the Probe Response frames from hapd"""
    dev.request("VENDOR_ELEM_ADD 14 " + elems)
    try:
        dev.scan(freq="2412", only_new=True)
    finally:
        dev.request("VENDOR_ELEM_REMOVE 14 *")
    time.sleep(0.1)
    out = run_tshark(os.path.join(params['logdir'], "hwsim0.pcapng"),
                     "wlan.fc.type_subtype == 5 && wlan.sa == " +
                     hapd.own_addr(), display=["wlan.da"])
    return out.splitlines()

def oce_ap_params(ssid):
    return {"ssid": ssid, "mbo": "1", "oce": "4", "beacon_int": "100"}

def test_oce_ap_capab(dev, apdev):
    """OCE AP advertises the OCE Capability Indication attribute"""
    hapd = hostapd.add_ap(apdev[0], oce_ap_params("test-oce"))
    dev[0].scan_for_bss(hapd.own_addr(), freq="2412")
    ie = bytes.fromhex(dev[0].get_bss(hapd.own_addr())['ie'])
    found = False
    while len(ie) >= 2:
        eid, elen, data = ie[0], ie[1], ie[2:2 + ie[1]]
        ie = ie[2 + elen:]
        if eid == 221 and data[0:4] == b'\x50\x6f\x9a\x16':
            attrs = data[4:]
            while len(attrs) >= 2:
                if attrs[0] == 101 and attrs[1] == 1:
                    if attrs[2] & 0x07 != 1:
                        raise Exception("Unexpected OCE release")
                    found = True
                attrs = attrs[2 + attrs[1]:]
    if not found:
        raise Exception("No OCE Capability Indication attribute")

def test_oce_ap_probe_suppress_ssid(dev, apdev, params):
    """OCE AP and Probe Suppression SSIDs attribute"""
    ssid = "test-oce"
    hapd = hostapd.add_ap(apdev[0], oce_ap_params(ssid))
    short_ssid = struct.pack('<I', binascii.crc32(ssid.encode()) & 0xffffffff)
    da = oce_probe_resp_da(dev[0], hapd, params,
                           "dd0a506f9a16" + "6a04" + short_ssid.hex())
    if dev[0].own_addr() in da:
        raise Exception("Probe Response frame sent despite suppression")
    other = struct.pack('<I', binascii.crc32(b"other") & 0xffffffff)
    da = oce_probe_resp_da(dev[0], hapd, params,
                           "dd0a506f9a16" + "6a04" + other.hex())
    if dev[0].own_addr() not in da:
        raise Exception("No Probe Response frame for another short SSID")

def test_oce_ap_probe_suppress_bssid(dev, apdev, params):
    """OCE AP and Probe Suppression BSSIDs attribute"""
    hapd = hostapd.add_ap(apdev[0], oce_ap_params("test-oce"))
    bssid = hapd.own_addr().replace(':', '')
    da = oce_probe_resp_da(dev[0], hapd, params,
                           "dd0c506f9a16" + "6906" + bssid)
    if dev[0].own_addr() in da:
        raise Exception("Probe Response frame sent despite suppression")
    # An empty list suppresses the responses from all OCE APs
    da = oce_probe_resp_da(dev[0], hapd, params, "dd06506f9a16" + "6900")
    if dev[0].own_addr() in da:
        raise Exception("Probe Response frame sent despite suppression")

def test_oce_ap_bcast_probe_resp(dev, apdev, params):
    """OCE AP sends broadcast Probe Response to an OCE STA"""
    hapd = hostapd.add_ap(apdev[0], oce_ap_params("test-oce"))
    da = oce_probe_resp_da(dev[0], hapd, params,
                           "dd07506f9a16" + "650101")
    if "ff:ff:ff:ff:ff:ff" not in da:
        raise Exception("No broadcast Probe Response frame")
    if dev[0].own_addr() in da:
        raise Exception("Unexpected unicast Probe Response frame")

def test_oce_ap_probe_max_channel_time(dev, apdev, params):
    """OCE AP leaves Probe Request with a long Max Channel Time to Beacons"""
    hapd = hostapd.add_ap(apdev[0], oce_ap_params("test-oce"))
    # FILS Request Parameters: no criteria, Max Channel Time 100 TUs
    da = oce_probe_resp_da(dev[0], hapd, params, "ff03020064")
    if dev[0].own_addr() in da:
        raise Exception("Probe Response frame sent despite Beacon within Max Channel Time")
    da = oce_probe_resp_da(dev[0], hapd, params, "ff0302000a")
    if dev[0].own_addr() not in da:
        raise Exception("No Probe Response frame with a short Max Channel Time")
