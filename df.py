#!/usr/bin/python3
# -*- coding:utf-8 -*-
__author__  = "Kim, Taehoon(kimfrancesco@gmail.com)"


import os
import stat
import json
import argparse
import time
from subprocess import Popen, PIPE
from dfbase import DFbase
from dflogging import *

banner = """ 
(    \ /  \  / __)(  / )(  __)(  _ \  (  __)/  \(  _ \(  __)(  ( \/ ___)(  )/ __)/ ___)
 ) D ((  O )( (__  )  (  ) _)  )   /   ) _)(  O ))   / ) _) /    /\___ \ )(( (__ \___ \\
(____/ \__/  \___)(__\_)(____)(__\_)  (__)  \__/(__\_)(____)\_)__)(____/(__)\___)(____/        
 """

class DockerForensics(DFbase):
    """
    Docker forensics
    """
    def __init__(self):
        super().__init__()


def main():
    print(banner)
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--container_id', required=True, action='store')
    args = parser.parse_args()

    df = DockerForensics()
    if df.check_privilege() is False:
        print('This script should be run with root privilege')
        exit(0)

    df.get_details_using_inspect_command(args.container_id)

    if df.setup_config() is False:
        exit(0)

    df.save_inspect_for_container()

    """
          USER        PID        PPID        COMMAND
          root        10677      10660       nginx: master process nginx -g daemon off;
    """
    df.get_processes_list_within_container()



    """
        - Overlay2
        Driver:overlay2, UppderDir:/var/lib/docker/overlay2/97bb052877bbb8d17db56473ba7bbc58ddd57aea25c6a451b338d139f93b77bc/diff
        [Found] Character device file: /var/lib/docker/overlay2/97bb052877bbb8d17db56473ba7bbc58ddd57aea25c6a451b338d139f93b77bc/diff/etc/logrotate.d, mtime:Sun Aug 26 21:26:35 2018, size:0
        [Found] Character device file: /var/lib/docker/overlay2/97bb052877bbb8d17db56473ba7bbc58ddd57aea25c6a451b338d139f93b77bc/diff/var/log/lastlog, mtime:Sat Aug 25 21:11:23 2018, size:0

        - Aufs
        root@ubuntu:~/docker-forensics# python3 search_whiteout.py -i adb
        [Found] WhiteOut(.wh.*) files: /var/lib/docker/aufs/diff/71c4ee29aed2bb070e3cc504e3633e0bff4413f591370e9ae7fe10bc77c14835/.wh..wh.aufs, mtime:Sat Sep 15 21:11:47 2018, size:0
        [Found] WhiteOut(.wh.*) Directories: /var/lib/docker/aufs/diff/71c4ee29aed2bb070e3cc504e3633e0bff4413f591370e9ae7fe10bc77c14835/.wh..wh.orph, mtime:Sat Sep 15 21:11:47 2018, size:4096
        [Found] WhiteOut(.wh.*) Directories: /var/lib/docker/aufs/diff/71c4ee29aed2bb070e3cc504e3633e0bff4413f591370e9ae7fe10bc77c14835/.wh..wh.plnk, mtime:Sat Sep 15 21:11:47 2018, size:4096
        [Found] WhiteOut(.wh.*) files: /var/lib/docker/aufs/diff/71c4ee29aed2bb070e3cc504e3633e0bff4413f591370e9ae7fe10bc77c14835/var/log/.wh.lastlog, mtime:Sat Sep 15 21:11:47 2018, size:0
        [Found] WhiteOut(.wh.*) files: /var/lib/docker/aufs/diff/71c4ee29aed2bb070e3cc504e3633e0bff4413f591370e9ae7fe10bc77c14835/var/log/.wh.faillog, mtime:Sat Sep 15 21:11:47 2018, size:0

    """

    df.get_timeinfo()
    df.get_uptime()
    df.search_whiteout_files()
    df.copy_files_relatedto_container()
    df.get_log_on_journald_service()
    df.search_hidden_directory()
    df.get_changed_history_using_diff_command()
    df.get_network_session_list()

if __name__ == "__main__":
    main()