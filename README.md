# docker-forensics
This project is for gathering artifcacts on docker environment, mainly focused on docker container,
but related docker hosts's artifcacts will be included.

## Artifacts
1. [x] Whiteout: AUFS, Overlay/Overlay2.
2. [x] Binary and metadata of Process running within container.
3. [x] Result of *docker inspect command*
4. [x] specific files related to container: *config.v2.json, hostconfig.json, hostname, resolv.conf, resolv.conf.hash*
5. [x] related logs of container: *container_id.json*
6. [x] docker daemon related log (Journald only)
7. [x] search hidden diretory
8. [x] get changed files or directories


## How to run
```
1. Download docker-forensics scripts using git client (git clone) or Web browser
2. Rename config.json.example to config.json
3. sudo run df.py -i Container_id using python3, such as sudo python3 df.py -i Container_id
   *** df.py script should be run with root permission
```

