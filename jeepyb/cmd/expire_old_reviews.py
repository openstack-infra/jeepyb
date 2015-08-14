#!/usr/bin/env python
# Copyright (c) 2012 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# This script is designed to expire old code reviews that have not been touched
# using the following rules:
# 1. if negative comment and no recent activity, expire

import argparse
import json
import logging
import paramiko

import jeepyb.log as l

logger = logging.getLogger('expire_reviews')


def expire_patch_set(ssh, patch_id, patch_subject):
    message = ('Code review expired due to no recent activity'
               ' after a negative review. It can be restored using'
               ' the \`Restore Change\` button under the Patch Set'
               ' on the web interface.')
    command = ('gerrit review --abandon '
               '--message="{message}" {patch_id}').format(
                   message=message,
                   patch_id=patch_id)

    logger.info('Expiring: %s - %s: %s', patch_id, patch_subject, message)
    stdin, stdout, stderr = ssh.exec_command(command)
    if stdout.channel.recv_exit_status() != 0:
        logger.error(stderr.read())


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('user', help='The gerrit admin user')
    parser.add_argument('ssh_key', help='The gerrit admin SSH key file')
    parser.add_argument('--age', dest='age', default='1w',
                        help='The minimum age of a review to expire')
    l.setup_logging_arguments(parser)
    options = parser.parse_args()
    l.configure_logging(options)

    GERRIT_USER = options.user
    GERRIT_SSH_KEY = options.ssh_key
    EXPIRY_AGE = options.age

    logger.info('Starting expire reviews')
    logger.info('Connecting to Gerrit')

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('localhost', username=GERRIT_USER,
                key_filename=GERRIT_SSH_KEY, port=29418)

    # Query all reviewed with no activity for 1 week
    logger.info('Searching no activity on negative review for 1 week')
    stdin, stdout, stderr = ssh.exec_command(
        'gerrit query --current-patch-set --all-approvals'
        ' --format JSON status:reviewed age:' + EXPIRY_AGE)

    for line in stdout:
        row = json.loads(line)
        if 'rowCount' not in row:
            # Search for negative approvals
            for approval in row['currentPatchSet']['approvals']:
                if approval['value'] in ('-1', '-2'):
                    expire_patch_set(ssh,
                                     row['currentPatchSet']['revision'],
                                     row['subject'])
                    break

    logger.info('End expire review')

if __name__ == "__main__":
    main()
