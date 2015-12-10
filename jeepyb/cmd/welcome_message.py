#!/usr/bin/env python
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

# This is designed to be called by a gerrit hook.  It searched new
# patchsets for those from a first time commiter, then posts a helpful
# message welcoming them to the community and explaining the review process
#
# For example, this might be called as follows
# python welcome_message.py --change Ia1fea1eab3976f1a9cb89ceb3ce1c6c6a7e79c42
# --change-url \ https://review-dev.openstack.org/81 --project gtest-org/test \
# --branch master --uploader User A. Example (user@example.com) --commit \
# 05508ae633852469d2fd7786a3d6f1d06f87055b --patchset 1 patchset-merged \
# --ssh-user=user --ssh-key=/home/user/.ssh/id_rsa
# and if this was the first commit from "user@example.com", a message
# would be posted on review 81.


import argparse
import logging
import paramiko

import jeepyb.gerritdb
import jeepyb.log as l

BASE_DIR = '/home/gerrit2/review_site'

logger = logging.getLogger('welcome_reviews')


def is_newbie(uploader):
    """Determine if the owner of the patch is a first-timer."""

    # Retrieve uploader email
    try:
        searchkey = uploader[uploader.rindex("(") + 1:-1]
    except ValueError:
        logger.info('Couldnt get email for %s', uploader)
        return False

    # this query looks for all distinct patchsets for the given
    # user. If there's only 1, they're a first-timer.
    query = """SELECT COUNT(DISTINCT p.change_id + p.patch_set_id)
               FROM patch_sets p, account_external_ids a
               WHERE a.email_address = %s
               AND a.account_id = p.uploader_account_id;"""

    cursor = jeepyb.gerritdb.connect().cursor()
    cursor.execute(query, searchkey)
    data = cursor.fetchone()
    if data:
        if data[0] == 1:
            logger.info('We found a newbie: %s', uploader)
            return True
        else:
            return False


def post_message(commit, gerrit_user, gerrit_ssh_key, message_file):
    """Post a welcome message on the patch set specified by the commit."""

    default_text = """Thank you for your first contribution to OpenStack.

    Your patch will now be tested automatically by OpenStack testing frameworks
    and once the automatic tests pass, it will be reviewed by other friendly
    developers. They will give you feedback and may require you to refine it.

    People seldom get their patch approved on the first try, so don't be
    concerned if requested to make corrections. Feel free to modify your patch
    and resubmit a new change-set.

    Patches usually take 3 to 7 days to be reviewed so be patient and be
    available on IRC to ask and answer questions about your work. Also it
    takes generally at least a couple of weeks for cores to get around to
    reviewing code. The more you participate in the community the more
    rewarding it is for you. You may also notice that the more you get to know
    people and get to be known, the faster your patches will be reviewed and
    eventually approved. Get to know others and become known by doing code
    reviews: anybody can do it, and it's a great way to learn the code base.

    Thanks again for supporting OpenStack, we look forward to working with you.

    IRC: https://wiki.openstack.org/wiki/IRC
    Workflow: http://docs.openstack.org/infra/manual/developers.html
    Commit Messages: https://wiki.openstack.org/wiki/GitCommitMessages
    """

    if message_file:
        try:
            with open(message_file, 'r') as _file:
                welcome_text = _file.read()
        except (OSError, IOError):
            logger.exception("Could not open message file")
            welcome_text = default_text
    else:
        welcome_text = default_text

    # post the above message, using ssh.
    command = ('gerrit review '
               '--message="{message}" {commit}').format(
                   message=welcome_text,
                   commit=commit)
    logger.info('Welcoming: %s', commit)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('localhost', username=gerrit_user,
                key_filename=gerrit_ssh_key, port=29418)
    stdin, stdout, stderr = ssh.exec_command(command)
    stdout_text = stdout.read()
    stderr_text = stderr.read()
    ssh.close()
    if stdout_text:
        logger.debug('stdout: %s' % stdout_text)
    if stderr_text:
        logger.error('stderr: %s' % stderr_text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('hook')
    # common
    parser.add_argument('--change', default=None)
    parser.add_argument('--change-url', default=None)
    parser.add_argument('--project', default=None)
    parser.add_argument('--branch', default=None)
    parser.add_argument('--commit', default=None)
    parser.add_argument('--topic', default=None)
    parser.add_argument('--change-owner', default=None)
    # patchset-abandoned
    parser.add_argument('--abandoner', default=None)
    parser.add_argument('--reason', default=None)
    # change-merged
    parser.add_argument('--submitter', default=None)
    parser.add_argument('--newrev', default=None)
    # patchset-created
    parser.add_argument('--uploader', default=None)
    parser.add_argument('--patchset', default=None)
    parser.add_argument('--is-draft', default=None)
    parser.add_argument('--kind', default=None)
    # for Welcome Message
    parser.add_argument('--ssh-user', dest='ssh_user',
                        help='The gerrit welcome message user')
    parser.add_argument('--ssh-key', dest='ssh_key',
                        help='The gerrit welcome message SSH key file')
    parser.add_argument('--message-file', dest='message_file', default=None,
                        help='The gerrit welcome message')
    # Don't actually post the message
    parser.add_argument('--dryrun', dest='dryrun', action='store_true')
    parser.add_argument('--no-dryrun', dest='dryrun', action='store_false')
    parser.set_defaults(dryrun=False)
    l.setup_logging_arguments(parser)

    args = parser.parse_args()

    l.configure_logging(args)

    # they're a first-timer, post the message on 1st patchset
    if is_newbie(args.uploader) and args.patchset == '1' and not args.dryrun:
        post_message(args.commit, args.ssh_user, args.ssh_key,
                     args.message_file)

if __name__ == "__main__":
    main()
