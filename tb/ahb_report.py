"""ahb_report.py - one place that counts errors, like the UVM report server.

Every checker calls tb_error(); the test prints AHB_RESULT: PASS only if the count is 0.
Each message starts with 'UVM_ERROR @ <time>' so the log can be grepped like a UVM log.
"""
import logging
from collections import Counter

from cocotb.simtime import get_sim_time

ERRORS = Counter()          # tag -> count
_log = logging.getLogger("cocotb.ahb")
MAX_PRINT = 20              # print the first few of each tag, count all


def tb_error(tag, msg):
    ERRORS[tag] += 1
    if ERRORS[tag] <= MAX_PRINT:
        _log.error("UVM_ERROR @ %d ns [%s] %s", get_sim_time("ns"), tag, msg)


def tb_info(tag, msg):
    _log.info("UVM_INFO @ %d ns [%s] %s", get_sim_time("ns"), tag, msg)


def total_errors():
    return sum(ERRORS.values())
