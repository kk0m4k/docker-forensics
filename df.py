#!/usr/bin/python3
# -*- coding:utf-8 -*-
__author__  = "Kim, Taehoon(kimfrancesco@gmail.com)"


import argparse
from dfbase import DFbase
from dflogging import *

banner = """ 
(    \ /  \  / __)(  / )(  __)(  _ \  (  __)/  \(  _ \(  __)(  ( \/ ___)(  )/ __)/ ___)
 ) D ((  O )( (__  )  (  ) _)  )   /   ) _)(  O ))   / ) _) /    /\___ \ )(( (__ \___ \\
(____/ \__/  \___)(__\_)(____)(__\_)  (__)  \__/(__\_)(____)\_)__)(____/(__)\___)(____/        
 """

def main():
    """
        After creating an object from the class defined in the DFbase module,
        collect it by calling the object method for collecting the artifact.
    """

    print(banner)

    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--container_id',
                            required=True, action='store',
                            help='Please specifiy container id you want \
                            to collect artifacts.')
    args = parser.parse_args()

    df = DFbase()

    if not df.check_privilege():
        print('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                DFbase.LOG_INFO_COLOR,                                
                'This script should be run with root privilege'))
        log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                    DFbase.LOG_INFO_COLOR,                                
                    'This script should be run with root privilege'))
        exit(0)

    if not df.get_details_using_inspect_command(args.container_id):
        exit(0)

    if not df.setup_config():
        exit(0)

    df.save_inspect_for_container()
    df.get_processes_list_within_container()
    df.get_timeinfo()
    df.get_uptime()
    df.search_whiteout_files()
    df.copy_files_relatedto_container()
    df.get_log_on_journald_service()
    df.search_hidden_directory()
    df.get_changed_history_using_diff_command()
    df.get_network_session_list()
    df.get_passwd_file()

if __name__ == "__main__":
    main()