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

# This is designed to be called by a gerrit hook.  It searched new
# patchsets for strings like "bug FOO" and updates corresponding Launchpad
# bugs status.

# You want to test this? I use a command line a bit like this:
#     python notify_impact.py --change 55607 \
#     --change-url https://review.openstack.org/55607 --project nova/ \
#     --branch master --commit c262de4417d48be599c3a7496ef94de5c84b188c \
#     --impact DocImpact --dest-address none@localhost --dryrun \
#     --config foo.yaml \
#     change-merged
#
# But you'll need a git repository at /home/gerrit2/review_site/git/nova.git
# for that to work

from __future__ import print_function

import argparse
import logging
import os
import re
import smtplib
import subprocess

from email.mime import text
from launchpadlib import launchpad
from launchpadlib import uris
import yaml

from jeepyb import projects


logger = logging.getLogger('notify_impact')

DOC_TAG = "doc"
BASE_DIR = '/home/gerrit2/review_site'
EMAIL_TEMPLATE = """
Hi, I'd like you to take a look at this patch for potential
%s.
%s

Log:
%s
"""

GERRIT_CACHE_DIR = os.path.expanduser(
    os.environ.get('GERRIT_CACHE_DIR',
                   '~/.launchpadlib/cache'))
GERRIT_CREDENTIALS = os.path.expanduser(
    os.environ.get('GERRIT_CREDENTIALS',
                   '~/.launchpadlib/creds'))


class BugActionsReal(object):
    """Things we do to bugs."""

    def __init__(self, lpconn):
        self.lpconn = lpconn

    def create(self, project, bug_title, bug_descr, args):
        # If the bug report is not targeting the 'openstack-manuals'
        # project, add an extra doc tag to make the bug easier to
        # look up.
        lp_target_project = str(project).split('/')[-1]
        tags = args.project.split('/')[1]
        if lp_target_project != 'openstack-manuals':
            tags = [tags, DOC_TAG]

        buginfo = self.lpconn.bugs.createBug(
            target=project, title=bug_title,
            description=bug_descr, tags=tags)
        buglink = buginfo.web_link
        return buginfo, buglink

    def subscribe(self, buginfo, subscriber):
        user = self.lpconn.people[subscriber]
        if user:
            buginfo.subscribe(person=user)


class BugActionsDryRun(object):
    def __init__(self, lpconn):
        self.lpconn = lpconn

    def create(self, project, bug_title, bug_descr, args):
        print('I would have created a bug in %s, but I am in dry run mode.\n\n'
              'Title: %s\n'
              'Description:\n'
              '%s' % (project, bug_title, bug_descr))
        return None, None

    def subscribe(self, buginfo, subscriber):
        print('I would have added %s as a subscriber to the bug, '
              'but I am in dry run mode' % subscriber)


def create_bug(git_log, args, config):
    """Create a bug for a change.

    Create a launchpad bug in a LP project, titled with the first line of
    the git commit message, with the content of the git_log prepended
    with the Gerrit review URL. Tag the bug with the name of the repository
    it came from. Returns link to the bug.
    """

    # Determine what LP project to use
    prelude = ('\nDear bug triager. This bug was created since a '
               'commit was marked with DOCIMPACT.\n')
    project_name = args.project.rstrip('/')
    lp_project = projects.docimpact_target(project_name)
    if lp_project == 'unknown':

        prelude = ('\nDear bug triager. This bug was created since a '
                   'commit was marked with DOCIMPACT.\n'
                   'Your project "%s" is set up so that we directly report '
                   'the documentation bugs against it. If this needs '
                   'changing, the docimpact-group option needs to be added '
                   'for the project. You can ask the '
                   'OpenStack infra team (#openstack-infra on freenode) for '
                   'help if you need to.\n'
                   % args.project)
        lp_project = project_name

    lpconn = launchpad.Launchpad.login_with(
        'Gerrit User Sync',
        uris.LPNET_SERVICE_ROOT,
        GERRIT_CACHE_DIR,
        credentials_file=GERRIT_CREDENTIALS,
        version='devel')

    if args.dryrun:
        actions = BugActionsDryRun(lpconn)
    else:
        actions = BugActionsReal(lpconn)

    lines_in_log = git_log.split('\n')
    bug_title = lines_in_log[4]
    bug_descr = args.change_url + prelude + '\n' + git_log
    project = lpconn.projects[lp_project]

    buglink = None
    author_class = None

    buginfo, buglink = actions.create(project, bug_title, bug_descr, args)
    logger.info('Created a bug in project %(project)s with title "%(title)s": '
                '%(buglink)s'
                % {'project': project,
                   'title': bug_title,
                   'buglink': buglink})

    # If the author of the merging patch matches our configured
    # subscriber lists, then subscribe the configured victims.
    for email_address in config.get('author_map', {}):
        email_re = re.compile('^Author:.*%s.*' % email_address)
        for line in bug_descr.split('\n'):
            m = email_re.match(line)
            if m:
                author_class = config['author_map'][email_address]

    if author_class:
        config = config.get('subscriber_map', {}).get(author_class, [])
        for subscriber in config:
            actions.subscribe(buginfo, subscriber)
            logger.info('Subscribed %(subscriber)s to bug %(buglink)s'
                        % {'subscriber': subscriber,
                           'buglink': buglink})

    return buglink


def smtp_connection(args):
    """Create SMTP connection based on command line arguments, falling
    back to sensible defaults if no arguments are provided.
    """
    conn = None
    if args.smtp_ssl:
        port = 465 if not args.smtp_port else args.smtp_port
        conn = smtplib.SMTP_SSL(args.smtp_host, port)
    else:
        port = 25 if not args.smtp_port else args.smtp_port
        conn = smtplib.SMTP(args.smtp_host, port)

    if args.smtp_starttls:
        conn.starttls()
        conn.ehlo()

    if args.smtp_user and args.smtp_pass:
        conn.login(args.smtp_user, args.smtp_pass)

    return conn


def process_impact(git_log, args, config):
    """Process DocImpact flag.

    If the 'DocImpact' flag is present for a change that is merged,
    create a new documentation bug in
    the openstack-manuals launchpad project based on the git_log.
    For non-documentation impacts at all states of merge
    notify the mailing list of impact.
    """
    if args.impact.lower() == 'docimpact':
        if args.hook == "change-merged":
            create_bug(git_log, args, config)
        return

    email_content = EMAIL_TEMPLATE % (args.impact,
                                      args.change_url, git_log)

    msg = text.MIMEText(email_content)
    msg['Subject'] = '[%s] %s review request change %s' % \
        (args.project, args.impact, args.change)
    msg['From'] = args.smtp_from
    msg['To'] = args.dest_address

    s = smtp_connection(args)
    s.sendmail(args.smtp_from, args.dest_address, msg.as_string())
    s.quit()


def impacted(git_log, impact_string):
    """Determine if a changes log indicates there is an impact."""
    return re.search(impact_string, git_log, re.IGNORECASE)


def extract_git_log(args):
    """Extract git log of all merged commits."""
    cmd = ['git',
           '--git-dir=' + BASE_DIR + '/git/' + args.project + '.git',
           'log', '--no-merges', args.commit + '^1..' + args.commit]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()[0]


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

    # Not passed by gerrit:
    parser.add_argument('--impact', default=None)
    parser.add_argument('--dest-address', default=None)

    # Automatic config: config contains a mapping of email addresses to
    # subscribers.
    parser.add_argument('--config', type=argparse.FileType('r'),
                        default=None)

    # Don't actually create the bug
    parser.add_argument('--dryrun', dest='dryrun', action='store_true')
    parser.add_argument('--no-dryrun', dest='dryrun', action='store_false')
    parser.set_defaults(dryrun=False)

    # SMTP configuration
    parser.add_argument('--smtp-from', dest='smtp_from',
                        default='gerrit2@review.openstack.org')

    parser.add_argument('--smtp-host', dest='smtp_host', default="localhost")
    parser.add_argument('--smtp-port', dest='smtp_port')

    parser.add_argument('--smtp-ssl', dest='smtp_ssl', action='store_true')
    parser.add_argument('--smtp-starttls', dest='smtp_starttls',
                        action='store_true')

    parser.add_argument('--smtp-user', dest='smtp_user',
                        default=os.getenv('SMTP_USER'))
    parser.add_argument('--smtp-pass', dest='smtp_pass',
                        default=os.getenv('SMTP_PASS'))

    args = parser.parse_args()

    # NOTE(mikal): the basic idea here is to let people watch
    # docimpact bugs filed by people of interest. For example
    # my team's tech writer wants to be subscribed to all the
    # docimpact bugs we create. The config for that would be
    # something like:
    #
    # author_map:
    #     mikal@stillhq.com: rcbau
    #     grumpy@dwarves.com: rcbau
    #
    # subscriber_map:
    #     rcbau: ['mikalstill', 'grumpypants']
    #
    # Where the entries in the author map are email addresses
    # to match in author lines, and the subscriber map is a
    # list of launchpad user ids.
    config = {}
    if args.config:
        config = yaml.load(args.config.read())

    # Get git log
    git_log = extract_git_log(args)

    # Process impacts found in git log
    if impacted(git_log, args.impact):
        process_impact(git_log, args, config)

if __name__ == "__main__":
    main()
