
#!/usr/bin/python3
# -*- coding:utf-8 -*-

__author__  = "Kim, Taehoon(kimfrancesco@gmail.com)"

import os
import sys
import stat
import time
import json
import hashlib
import re
from subprocess import Popen, PIPE
from dflogging import *


DOCKER_INSPECT_CMD = "docker inspect {}"
DOCKER_TOP_CMD = "docker top {} -eo user,pid,ppid,stime,command"
DOCKER_DIFF_CMD = "docker diff {}"
DOCKER_DATE_CMD = "docker exec -it {} date"
DOCKER_UPTIME_CMD = "docker exec -it {} uptime"
DOCKER_CP_FROM_CONTAINER_TO_HOST_CMD = "docker cp {}:{} {}"
NSENTER_CMD = "nsenter -t {} -n lsof -i"
READLINK_CMD = "readlink  {}"

LOG_JOURNALD = "journalctl -u docker -o json > {}/jouranld_docker.json"

AUFS_IMAGE_BASE_PATH = "/var/lib/docker/aufs/"
AUFS_IMAGE_LAYERDB_PATH = "/var/lib/docker/image/aufs/layerdb/mounts/"
AUFS_WHITEOUT_PREFIX = ".wh."

HIDDEN_DIR_REGX = "^[.\s].*$"

class DFbase():
    LOG_ERROR_COLOR ='\x1b[31;1m'
    LOG_WARNING_COLOR ='\x1b[33;1m'
    LOG_INFO_COLOR ='\x1b[0m'
    LOG_DEBUG_COLOR ='\x1b[35m'

    def __init__(self):
        self.storage_driver = ""
        self.pid = 0
        self.data = {}

        self.IS_OVERLAYFS = False
        self.IS_AUFSFS = False
        self.overlay_merged_path = ""
        self.aufs_mnt_path = ""
        self.aufs_container_branch_path = ""
        self.aufs_container_layerdb_path = ""

        df_log_initialize()

    def check_privilege(self):
        log.debug('{}[*]{} run with GETUID:{}'.format(DFbase.LOG_DEBUG_COLOR, DFbase.LOG_INFO_COLOR, os.getuid()))
        return True if (os.getuid() == 0) else False

    def get_details_using_inspect_command(self, container_id):
        """ To get detailed information about container using inspect command

        * Only supported Storage drivers are OVERLAY,OVERLAY2 and AUFS

        Args:
            container_id (str): container id to be inspected
        Returns
            bool: True if successful, False otherwise.
        """

        try:
            p = Popen(DOCKER_INSPECT_CMD.format(container_id), shell=True, stdout=PIPE, stderr=PIPE)
            data_dump, stderr_data = p.communicate()
            log.debug('{}[*]{} Inspect result:{}'.format(DFbase.LOG_DEBUG_COLOR,
                        DFbase.LOG_INFO_COLOR, 
                        json.dumps(json.loads(data_dump)),indent=4))

        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                        DFbase.LOG_INFO_COLOR, e))
            return False

        self.data = json.loads(data_dump.decode('utf-8'))

        if not self.data:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                        DFbase.LOG_INFO_COLOR,
                        'Please check if container id is valid'))
            return False

        self.storage_driver = self.data[0]['Driver']
        self.pid = self.data[0]['State']['Pid']
        self.container_id = self.data[0]['Id']

        log.debug('{}[*]{} Storage Driver: {}'.format(DFbase.LOG_DEBUG_COLOR,
                   DFbase.LOG_INFO_COLOR, self.storage_driver))
        if self.storage_driver == 'overlay2' or self.storage_driver == 'overlay':
            self.IS_OVERLAYFS = True
            self.overlay_upperdir_path = self.data[0]['GraphDriver']['Data']['UpperDir']
            self.overlay_merged_path = self.data[0]['GraphDriver']['Data']['MergedDir']
        elif self.storage_driver == 'aufs':
            self.IS_AUFSFS = True
            self.aufs_container_layerdb_path = AUFS_IMAGE_LAYERDB_PATH + self.data[0]['Id']
        else:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_DEBUG_COLOR,
                        DFbase.LOG_INFO_COLOR,
                        'This storage driver does not support'))
            False

        log.debug('{}[*]{} Container id: {}'.format(DFbase.LOG_DEBUG_COLOR,
                        DFbase.LOG_INFO_COLOR, self.container_id))
        return True


    def setup_config(self):
        """ To parse config.json file
            Returns 
                bool: True if successful, False otherwise.
        """

        try:
            with open('config.json') as f:
                config = json.load(f)
        except FileNotFoundError as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                        DFbase.LOG_INFO_COLOR, e))
            print('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                    DFbase.LOG_INFO_COLOR, 
                    'Please copy config.json.example to confing.json'))
            return False
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR, e))
            return False

        self.artifacts_path = config['ARTIFACTS']['BASE_PATH'].format(self.container_id)
        self.executable_path = config['ARTIFACTS']['EXECUTABLE_PATH']
        self.executable_path = self.executable_path.replace('BASE_PATH', self.artifacts_path)
        self.diff_files_path = config['ARTIFACTS']['DIFF_FILES_PATH']
        self.diff_files_path = self.diff_files_path.replace('BASE_PATH', self.artifacts_path)
        self.log_journald = (True if config['ARTIFACTS']['LOG_JOURNALD_SERVICE'] == "TRUE" else False)

        for x_path in [self.artifacts_path, self.executable_path, self.diff_files_path]:
            if not os.path.exists(x_path):
                try:
                    os.makedirs(x_path, mode=0o700)
                except Exception as e:
                    log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                                DFbase.LOG_INFO_COLOR, e))
                    print('{}[*]{} {}:{}'.format(DFbase.LOG_ERROR_COLOR,
                            DFbase.LOG_INFO_COLOR,
                            'Failed when creating directory', x_path))
                    return False

        return True


    def save_inspect_for_container(self):
        inspect_output = self.artifacts_path + '/' + 'inspect_command.json'
        try:
            with open(inspect_output, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
                log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                            DFbase.LOG_INFO_COLOR, e))
                return False
        return True


    def get_processes_list_within_container(self):
        """ Get process list within container
            Retruns
                bool: True if successful, False otherwise.
        """
        items_list = []
        proc_item = []
        procs_dict = {}

        try:
            p = Popen(DOCKER_TOP_CMD.format(self.container_id), shell=True, stdout=PIPE, stderr=PIPE)
            stdout_dump, stderr_data = p.communicate()
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR,
                        DFbase.LOG_INFO_COLOR,e))
            return False

        procs_lines = stdout_dump.decode('utf-8')
        procs_lines = procs_lines.split("\n")

        for procs_item in procs_lines:
            if 'USER' in procs_item:
                continue
            elif len(procs_item):
                proc_item.append(procs_item)

        for item in proc_item:
            x = item.split(None, 4)
            log.debug('{}[*]{} PID:{}, {}, {}, {}, {}'.format(DFbase.LOG_DEBUG_COLOR, 
                        DFbase.LOG_INFO_COLOR, x[0], x[1],x[2],x[3],x[4]))
            procs_dict['USER'] = x[0]
            procs_dict['PID'] = x[1]
            procs_dict['PPID'] = x[2]
            procs_dict['STIME'] = x[3]
            procs_dict['CMD'] = x[4]

            items_list.append(procs_dict.copy())

        procs_path = self.artifacts_path + '/' + 'top_command.json'
        with open(procs_path, 'w') as f:
            json.dump(items_list, f, indent=4)

        self.copy_executable(items_list)

        return True


    def copy_executable(self, procs_list):
        proc_list = []
        md5sum = ""
        for proc in procs_list:
            proc_path = '/proc/' + proc.get('PID') + '/exe'
            try:
                p = Popen(READLINK_CMD.format(proc_path), shell=True, stdout=PIPE, stderr=PIPE)
                stdout_dump, stderr_data = p.communicate()
            except Excpetion as e:
                log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                            DFbase.LOG_INFO_COLOR, e))
                continue

            exe_path = stdout_dump.decode('utf-8')

            if exe_path and self.IS_OVERLAYFS:
                if os.path.isfile('{}{}'.format(self.overlay_merged_path, exe_path.strip('\n'))):
                    md5sum = self.get_md5sum('{}{}'.format(self.overlay_merged_path, exe_path.strip('\n')))
                    log.debug('{}[*]{} md5sum:{}'.format(DFbase.LOG_DEBUG_COLOR, 
                                DFbase.LOG_INFO_COLOR, md5sum))
                    COPY_CMD = 'cp -f {}{} {}{}_{}'.format(self.overlay_merged_path, exe_path.strip('\n'), self.executable_path,exe_path.rsplit('/', 1)[1].strip('\n'), md5sum)
                    log.debug('{}[*]{} PID:{}, CMD:{}'.format(DFbase.LOG_DEBUG_COLOR, 
                                DFbase.LOG_INFO_COLOR, proc.get('PID'), COPY_CMD))
                    os.system(COPY_CMD)
                    proc['EXECUTABLE'] = '{}{}'.format(self.overlay_merged_path, exe_path.strip('\n'))
                else:
                    proc['EXECUTABLE'] = 'NOT FOUND - {}{}'.format(self.overlay_merged_path, exe_path.strip('\n'))

            elif exe_path and self.IS_AUFSFS:
                self.aufs_mnt_path = self.get_aufs_container_mnt_path()
                if os.path.isfile('{}{}'.format(self.aufs_mnt_path, exe_path.strip('\n'))):
                    self.aufs_mnt_path = self.get_aufs_container_mnt_path()
                    md5sum = self.get_md5sum('{}{}'.format(self.aufs_mnt_path,  exe_path.strip('\n')))
                    log.debug('{}[*]{} md5sum:{}'.format(DFbase.LOG_DEBUG_COLOR, 
                                DFbase.LOG_INFO_COLOR, md5sum))
                    COPY_CMD = 'cp -f {}{} {}{}_{}'.format(self.aufs_mnt_path, exe_path.strip('\n'), self.executable_path, exe_path.rsplit('/', 1)[1].strip('\n'), md5sum)
                    log.debug('{}[*]{} PID:{}, CMD:{}'.format(DFbase.LOG_DEBUG_COLOR, 
                                DFbase.LOG_INFO_COLOR, proc.get('PID'), COPY_CMD))
                    os.system(COPY_CMD)
                    proc['EXECUTABLE'] = '{}{}'.format(self.aufs_mnt_path, exe_path.strip('\n'))
                else:
                    proc['EXECUTABLE'] = 'NOT FOUND - {}{}'.format(self.aufs_mnt_path, exe_path.strip('\n'))

            proc['MD5'] = md5sum
            proc_list.append(proc.copy())

        procs_path = self.artifacts_path + '/' + 'process.json'
        with open(procs_path, 'w') as f:
            json.dump(proc_list, f, indent=4)

        return True


    def get_aufs_container_mnt_path(self):
        mountid_file = self.aufs_container_layerdb_path + '/mount-id'
        with open(mountid_file, 'r') as fd:
            line = fd.readline()
        return AUFS_IMAGE_BASE_PATH + 'mnt/' + line

    def get_md5sum(self, filepath):
        log.debug('{}[*]{} md5sum target file:{}'.format(DFbase.LOG_DEBUG_COLOR, 
                    DFbase.LOG_INFO_COLOR, filepath))
        md5sum = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    md5sum.update(data)
        except Exception as e:
            print(e)
            return False

        return md5sum.hexdigest()

    def search_whiteout_files(self):
        if self.IS_OVERLAYFS:
            path = self.get_overlay_upperlayer_path()
            self.search_files_with_character_device(path)
        elif self.IS_AUFSFS:
            path = self.get_aufs_container_branch_path()
            self.search_files_with_wh_prefix(path)

    def get_overlay_upperlayer_path(self):
        return self.overlay_upperdir_path

    def get_aufs_container_branch_path(self):
        mountid_file = self.aufs_container_layerdb_path + '/mount-id'
        with open(mountid_file, 'r') as fd:
            line = fd.readline()
        return AUFS_IMAGE_BASE_PATH + 'diff/' + line

    def search_files_with_character_device(self, arg_path):
        overlay_wh_list = []
        overlay_whiteout = {}
        for dirpath, dirs, files in os.walk(arg_path):
            for filename in files:
                fname = os.path.join(dirpath, filename)
                mode = os.stat(fname).st_mode
                if stat.S_ISCHR(mode):
                    log.debug('[Found] Character device file: {}, mtime:{}, size:{}'.format(fname, time.ctime(
                        os.stat(fname).st_mtime), os.stat(fname).st_size))
                    overlay_whiteout['file_type'] = 'CHARDEV'
                    overlay_whiteout['fname'] = fname
                    overlay_whiteout['mtime'] = time.ctime(os.stat(fname).st_mtime)
                    overlay_whiteout['size'] = os.stat(fname).st_size
                    overlay_wh_list.append(overlay_whiteout.copy())

        overlay_wh_path = self.artifacts_path + '/' + 'whiteout.json'
        if len(overlay_wh_list):
            with open(overlay_wh_path, 'w') as f:
                json.dump(overlay_wh_list, f, indent=4)

    def search_files_with_wh_prefix(self, arg_path):
        aufs_wh_list = []
        aufs_whiteout = {}
        for dirpath, dirs, files in os.walk(arg_path):
            for filename in files:
                if filename.startswith(AUFS_WHITEOUT_PREFIX):
                    fname = os.path.join(dirpath, filename)
                    log.debug('[Found] WhiteOut(.wh.*) files: {}, mtime:{}, size:{}'.format(fname, time.ctime(
                        os.stat(fname).st_mtime), os.stat(fname).st_size))
                    aufs_whiteout['file_type'] = 'FILE'
                    aufs_whiteout['fname'] = fname
                    aufs_whiteout['mtime'] = time.ctime(os.stat(fname).st_mtime)
                    aufs_whiteout['size'] = os.stat(fname).st_size
                    aufs_wh_list.append(aufs_whiteout.copy())

            for dir in dirs:
                if dir.startswith(AUFS_WHITEOUT_PREFIX):
                    dirname = os.path.join(dirpath, dir)
                    print('[Found] WhiteOut(.wh.*) Directories: {}, mtime:{}, size:{}'.format(dirname, time.ctime(
                        os.stat(dirname).st_mtime), os.stat(dirname).st_size))
                    aufs_whiteout['file_type'] = 'DIRECTORY'
                    aufs_whiteout['fname'] = dirname
                    aufs_whiteout['mtime'] = time.ctime(os.stat(dirname).st_mtime)
                    aufs_whiteout['size'] = os.stat(dirname).st_size
                    aufs_wh_list.append(aufs_whiteout.copy())

        aufs_wh_path = self.artifacts_path + '/' + 'whiteout.json'
        if len(aufs_wh_list):
            with open(aufs_wh_path, 'w') as f:
                json.dump(aufs_wh_list, f, indent=4)


    def copy_files_relatedto_container(self):
        container_path = "/var/lib/docker/containers/{}".format(self.container_id)

        for dirpath, dirs, files in os.walk(container_path):
            for file in files:
                log.debug("{}[*]{} dirpath:{}, dirs:{}, files:{}"
                            .format(DFbase.LOG_DEBUG_COLOR,
                            DFbase.LOG_INFO_COLOR,
                            dirpath, dirs, files))
                COPY_CMD = 'cp -f {}/{} {}'.format(dirpath, file, self.artifacts_path)
                os.system(COPY_CMD)


    def get_log_on_journald_service(self):
        if self.log_journald is False:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR,
                        'This docker host does not use journald system'))
            return False

        try:
            p = Popen(LOG_JOURNALD.format(self.artifacts_path), shell=True, stdout=PIPE, stderr=PIPE)
            stdout_dump, stderr_data = p.communicate()
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR, e))
            return False

        return True


    def search_hidden_directory(self):
        hidden_dirs_info = {}
        hidden_dirs_list = []

        if self.IS_OVERLAYFS:
            path = self.get_overlay_upperlayer_path()
        elif self.IS_AUFSFS:
            path = self.get_aufs_container_branch_path()

        p = re.compile(HIDDEN_DIR_REGX)
        for dirpath, dir_entities, files in os.walk(path):
            for dir_entity in dir_entities:
                s = p.search(dir_entity)
                if s is not None:
                    dirname = os.path.join(dirpath, dir_entity)
                    print('[Found] Hidden Directory: {}, mtime:{}, size:{}'.format(dirname, time.ctime(
                        os.stat(dirname).st_mtime), os.stat(dirname).st_size))
                    hidden_dirs_info['directory'] = dirname
                    hidden_dirs_info['mtime'] = time.ctime(os.stat(dirname).st_mtime)
                    hidden_dirs_info['size'] = os.stat(dirname).st_size
                    hidden_dirs_list.append(hidden_dirs_info.copy())

        hidden_path = self.artifacts_path + '/' + 'hidden_directory.json'
        if len(hidden_dirs_list):
            with open(hidden_path, 'w') as f:
                json.dump(hidden_dirs_list, f, indent=4)

        return True


    def get_changed_history_using_diff_command(self):
        diff_list = []

        if self.IS_OVERLAYFS:
            path = self.get_overlay_upperlayer_path()
        elif self.IS_AUFSFS:
            path = self.get_aufs_container_branch_path()

        try:
            p = Popen(DOCKER_DIFF_CMD.format(self.container_id), shell=True, stdout=PIPE, stderr=PIPE)
            diff_dump, stderr_data = p.communicate()
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR, e))
            return False

        changed_entities = diff_dump.decode('utf-8')
        changed_entities = changed_entities.split("\n")

        for diff_entity in changed_entities:
            diff_info = {}
            if not len(diff_entity):
                continue

            category, entity = diff_entity.split(maxsplit=1)

            diff_info[category] = entity
            absolute_path = '{}{}'.format(path,entity)
            diff_info['fullpath'] = absolute_path
            diff_info['exist'] = "YES" if os.path.exists(absolute_path) else "No"
            diff_info['mtime'] = time.ctime(os.stat(absolute_path).st_mtime) if os.path.exists(absolute_path) else "Null"
            diff_info['size'] = os.stat(absolute_path).st_size if os.path.exists(absolute_path) else "Null"
            diff_list.append(diff_info.copy())

        diff_path = self.artifacts_path + '/' + 'diff.json'
        if len(diff_list):
            with open(diff_path, 'w') as f:
                json.dump(diff_list, f, indent=4)
        
        for diff_entity in diff_list:
            if diff_entity['fullpath'] and self.IS_OVERLAYFS:
                log.debug('{}[*]{} DIFF_Overlay:{}'
                            .format(DFbase.LOG_DEBUG_COLOR,
                            DFbase.LOG_INFO_COLOR,
                            diff_entity['fullpath']))
                if os.path.isfile(diff_entity['fullpath']) and os.access(diff_entity['fullpath'], os.X_OK):
                    md5sum = self.get_md5sum('{}'.format(diff_entity['fullpath']))
                    log.debug('md5sum:{}'.format(md5sum))
                    COPY_CMD = 'cp -f {} {}{}_{}'.format(diff_entity['fullpath'], self.diff_files_path, diff_entity['fullpath'].rsplit('/', 1)[1], md5sum)
                    log.debug('DIFF CMD:{}'.format(COPY_CMD))
                    os.system(COPY_CMD)

            elif diff_entity['fullpath']  and self.IS_AUFSFS:
                log.debug('DIFF_Aufs:{}'.format(diff_entity['fullpath']))
                if os.path.isfile(diff_entity['fullpath']) and os.access(diff_entity['fullpath'], os.X_OK): 
                    md5sum = self.get_md5sum('{}'.format(diff_entity['fullpath']))
                    log.debug('md5sum:{}'.format(md5sum))
                    COPY_CMD = 'cp -f {} {}{}_{}'.format(diff_entity['fullpath'], self.diff_files_path, diff_entity['fullpath'].rsplit('/', 1)[1], md5sum)
                    log.debug('DIFF CMD:{}'.format(COPY_CMD))
                    os.system(COPY_CMD)

        return True

    
    def get_network_session_list(self):
        '''
            root@ubuntu:/proc/21960# nsenter -t 21960 -n lsof -i
            COMMAND     PID     USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
            apache2   22006     root    3u  IPv4 578777      0t0  TCP *:http (LISTEN)
            apache2   22013 www-data    3u  IPv4 578777      0t0  TCP *:http (LISTEN)
            apache2   22014 www-data    3u  IPv4 578777      0t0  TCP *:http (LISTEN)
            anotherdo 22149     root    2u  IPv4 578171      0t0  TCP *:8000 (LISTEN)
            anotherdo 22149     root    4u  IPv4 578172      0t0  TCP victim:8000->_gateway:54802 (ESTABLISHED)

        '''
        items_list = []
        network_item = []
        network_dict = {}

        try:
            p = Popen(NSENTER_CMD.format(self.pid), shell=True, stdout=PIPE, stderr=PIPE)
            network_dump, stderr_data = p.communicate()
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR, e))
            return False 

        network_lines = network_dump.decode('utf-8')
        network_lines = network_lines.split("\n")

        for network_line in network_lines:
            if 'COMMAND' in network_line:
                continue
            elif len(network_line):
                network_item.append(network_line)

        for item in network_item:
            x = item.split(maxsplit=8)
            log.debug('{}[*]{} NETWORK:{}, {}, {}, {}, {}, {}, {},{},{}'
                        .format(DFbase.LOG_DEBUG_COLOR,DFbase.LOG_INFO_COLOR,
                        x[0], x[1],x[2],x[3],x[4], x[5],x[6],x[7],x[8]))
            network_dict['COMMAND'] = x[0]
            network_dict['PID'] = x[1]
            network_dict['USER'] = x[2]
            network_dict['FD'] = x[3]
            network_dict['TYPE'] = x[4]
            network_dict['DEVICE'] = x[5]
            network_dict['SIZEOFF'] = x[6]
            network_dict['NODE'] = x[7]
            network_dict['NAME'] = x[8]

            items_list.append(network_dict.copy())

        network_path = self.artifacts_path + '/' + 'network_session.json'
        with open(network_path, 'w') as f:
            json.dump(items_list, f, indent=4)

        return True
    

    def get_timeinfo(self):

        items_list = []
        date_dict = {}

        try:
            p = Popen(DOCKER_DATE_CMD.format(self.container_id), shell=True, stdout=PIPE, stderr=PIPE)
            date_dump, stderr_data = p.communicate()
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR, e))
            return False

        date_info = date_dump.decode('utf-8')
        date_info = date_info.strip("\r\n")
        date_dict['TIME'] = date_info

        items_list.append(date_dict)
        log.debug('{}[*]{} timeinfo:{}'.format(DFbase.LOG_DEBUG_COLOR,
                    DFbase.LOG_INFO_COLOR, items_list))

        date_path = self.artifacts_path + '/' + 'datetime.json'
        with open(date_path, 'w') as f:
            json.dump(items_list, f, indent=4)

        return True


    def get_uptime(self):

        items_list = []
        uptime_dict = {}

        try:
            p = Popen(DOCKER_UPTIME_CMD.format(self.container_id), shell=True, stdout=PIPE, stderr=PIPE)
            uptime_dump, stderr_data = p.communicate()
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR, e))
            return False

        uptime_info = uptime_dump.decode('utf-8')
        uptime_info = uptime_info.strip("\r\n")
        uptime_dict['TIME'] = uptime_info

        items_list.append(uptime_dict)
        log.debug('{}[*]{} uptime:{}'.format(DFbase.LOG_DEBUG_COLOR,
                    DFbase.LOG_INFO_COLOR, items_list))

        uptime_path = self.artifacts_path + '/' + 'uptime.json'
        with open(uptime_path, 'w') as f:
            json.dump(items_list, f, indent=4)

        return True


    def get_passwd_file(self):
        try:
            p = Popen(DOCKER_CP_FROM_CONTAINER_TO_HOST_CMD.format(self.container_id, '/etc/passwd', self.artifacts_path), shell=True, stdout=PIPE, stderr=PIPE)
            dump, stderr_data = p.communicate()
        except Exception as e:
            log.debug('{}[*]{} {}'.format(DFbase.LOG_ERROR_COLOR, 
                        DFbase.LOG_INFO_COLOR, e))
            return False
        return True