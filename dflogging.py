#!/usr/bin/python3
# -*- coding:utf-8 -*-
__author__  = "Kim, Taehoon(kimfrancesco@gmail.com)"


import logging
import logging.handlers

LOGFILENAME="./debug.log"
LOGMAXSIZE = 1024 * 1024

log = logging.getLogger(__name__)
syslogUDP = logging.getLogger(__name__)


def df_log_initialize():
    log.setLevel(logging.DEBUG)
    log_Handler = logging.handlers.RotatingFileHandler(LOGFILENAME, maxBytes = LOGMAXSIZE, backupCount=1)
    log_format = logging.Formatter('[%(asctime)s|%(filename)s:%(lineno)s], %(message)s')
    log_Handler.setFormatter(log_format)
    log.addHandler(log_Handler)
