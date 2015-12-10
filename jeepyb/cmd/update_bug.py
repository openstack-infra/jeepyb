#!/usr/bin/env python
# Copyright (c) 2011 OpenStack, LLC.
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

import argparse
import os
import re
import subprocess

from launchpadlib import launchpad
from launchpadlib import uris

import jeepyb.gerritdb
from jeepyb import projects as p
from jeepyb import utils as u


BASE_DIR = '/home/gerrit2/review_site'
GERRIT_CACHE_DIR = os.path.expanduser(
    os.environ.get('GERRIT_CACHE_DIR',
                   '~/.launchpadlib/cache'))
GERRIT_CREDENTIALS = os.path.expanduser(
    os.environ.get('GERRIT_CREDENTIALS',
                   '~/.launchpadlib/creds'))


def fix_or_related_fix(related):
    if related:
        return "Related fix"
    else:
        return "Fix"


def add_change_abandoned_message(bugtask, change_url, project,
                                 branch, abandoner, reason):
    subject = ('Change abandoned on %s (%s)'
               % (u.short_project_name(project), branch))
    body = ('Change abandoned by %s on branch: %s\nReview: %s'
            % (abandoner, branch, change_url))

    if reason:
        body += ('\nReason: %s' % (reason))

    bugtask.bug.newMessage(subject=subject, content=body)


def add_change_proposed_message(bugtask, change_url, project, branch,
                                related=False):
    fix = fix_or_related_fix(related)
    subject = ('%s proposed to %s (%s)'
               % (fix, u.short_project_name(project), branch))
    body = '%s proposed to branch: %s\nReview: %s' % (fix, branch, change_url)
    bugtask.bug.newMessage(subject=subject, content=body)


def add_change_merged_message(bugtask, change_url, project, commit,
                              submitter, branch, git_log, related=False):
    subject = '%s merged to %s (%s)' % (fix_or_related_fix(related),
                                        u.short_project_name(project), branch)
    git_url = 'https://git.openstack.org/cgit/%s/commit/?id=%s' % (project,
                                                                   commit)
    body = '''Reviewed:  %s
Committed: %s
Submitter: %s
Branch:    %s\n''' % (change_url, git_url, submitter, branch)
    body = body + '\n' + git_log
    bugtask.bug.newMessage(subject=subject, content=body)


def set_in_progress(bugtask, launchpad, uploader, change_url):
    """Set bug In progress with assignee being the uploader"""

    # Retrieve uploader from Launchpad by correlating Gerrit E-mail
    # address to OpenID, and only set if there is a clear match.
    try:
        searchkey = uploader[uploader.rindex("(") + 1:-1]
    except ValueError:
        searchkey = uploader

    # The counterintuitive query is due to odd database schema choices
    # in Gerrit. For example, an account with a secondary E-mail
    # address added looks like...
    # select email_address,external_id from account_external_ids
    #     where account_id=1234;
    # +-----------------+-----------------------------------------+
    # | email_address   | external_id                             |
    # +-----------------+-----------------------------------------+
    # | plugh@xyzzy.com | https://login.launchpad.net/+id/fR0bnU1 |
    # | bar@foo.org     | mailto:bar@foo.org                      |
    # | NULL            | username:quux                           |
    # +-----------------+-----------------------------------------+
    # ...thus we need a join on a secondary query to search against
    # all the user's configured E-mail addresses.
    #
    query = """SELECT t.external_id FROM account_external_ids t
            INNER JOIN (
                SELECT t.account_id FROM account_external_ids t
                WHERE t.email_address = %s )
            original ON t.account_id = original.account_id
            AND t.external_id LIKE 'https://login.launchpad.net%%'"""

    cursor = jeepyb.gerritdb.connect().cursor()
    cursor.execute(query, searchkey)
    data = cursor.fetchone()
    if data:
        assignee = launchpad.people.getByOpenIDIdentifier(identifier=data[0])
        if assignee:
            bugtask.assignee = assignee

    bugtask.status = "In Progress"
    bugtask.lp_save()


def set_fix_committed(bugtask):
    """Set bug fix committed."""

    bugtask.status = "Fix Committed"
    bugtask.lp_save()


def set_fix_released(bugtask):
    """Set bug fix released."""

    bugtask.status = "Fix Released"
    bugtask.lp_save()


def release_fixcommitted(bugtask):
    """Set bug FixReleased if it was FixCommitted."""

    if bugtask.status == u'Fix Committed':
        set_fix_released(bugtask)


def tag_in_branchname(bugtask, branch):
    """Tag bug with in-branch-name tag (if name is appropriate)."""

    lp_bug = bugtask.bug
    branch_name = branch.replace('/', '-')
    if branch_name.replace('-', '').isalnum():
        lp_bug.tags = lp_bug.tags + ["in-%s" % branch_name]
        lp_bug.tags.append("in-%s" % branch_name)
        lp_bug.lp_save()


class Task:
    def __init__(self, lp_task, prefix):
        '''Prefixes associated with bug references will allow for certain
        changes to be made to the bug's launchpad (lp) page. The following
        tokens represent the automation currently taking place.

        ::
        add_comment       -> Adds a comment to the bug's lp page.
        sidenote          -> Adds a 'related' comment to the bug's lp page.
        set_in_progress   -> Sets the bug's lp status to 'In Progress'.
        set_fix_released  -> Sets the bug's lp status to 'Fix Released'.
        set_fix_committed -> Sets the bug's lp status to 'Fix Committed'.
        ::

        changes_needed, when populated, simply indicates the actions that are
        available to be taken based on the value of 'prefix'.
        '''
        self.lp_task = lp_task
        self.changes_needed = []

        # If no prefix was matched, default to 'closes'.
        prefix = prefix.split('-')[0].lower() if prefix else 'closes'

        if prefix in ('closes', 'fixes', 'resolves'):
            self.changes_needed.extend(('add_comment',
                                        'set_in_progress',
                                        'set_fix_committed',
                                        'set_fix_released'))
        elif prefix in ('partial',):
            self.changes_needed.extend(('add_comment', 'set_in_progress'))
        elif prefix in ('related', 'impacts', 'affects'):
            self.changes_needed.extend(('sidenote',))
        else:
            # prefix is not recognized.
            self.changes_needed.extend(('add_comment',))

    def needs_change(self, change):
        '''Return a boolean indicating if given 'change' needs to be made.'''
        if change in self.changes_needed:
            return True
        else:
            return False


def process_bugtask(launchpad, task, git_log, args):
    """Apply changes to lp bug tasks, based on hook / branch."""

    bugtask = task.lp_task
    series = None

    if args.hook == "change-abandoned":
        add_change_abandoned_message(bugtask, args.change_url,
                                     args.project, args.branch,
                                     args.abandoner, args.reason)

    if args.hook == "change-merged":
        if args.branch == 'master':
            if (not p.is_delay_release(args.project) and
                    task.needs_change('set_fix_released')):
                set_fix_released(bugtask)
            else:
                if (bugtask.status != u'Fix Released' and
                        task.needs_change('set_fix_committed')):
                    set_fix_committed(bugtask)
        elif args.branch.startswith('proposed/'):
            release_fixcommitted(bugtask)
        else:
            series = args.branch.rsplit('/', 1)[-1]

        if series:
            # Look for a related task matching the series.
            for reltask in bugtask.related_tasks:
                if (reltask.bug_target_name.endswith(series) and
                        reltask.status != u'Fix Released' and
                        task.needs_change('set_fix_committed')):
                    set_fix_committed(reltask)
                    break
            else:
                # Use tag_in_branchname if there isn't any.
                tag_in_branchname(bugtask, args.branch)

        if task.needs_change('add_comment') or task.needs_change('sidenote'):
            add_change_merged_message(bugtask, args.change_url, args.project,
                                      args.commit, args.submitter, args.branch,
                                      git_log,
                                      related=task.needs_change('sidenote'))

    if args.hook == "patchset-created":
        if args.branch == 'master':
            if (bugtask.status not in [u'Fix Committed', u'Fix Released'] and
                    task.needs_change('set_in_progress')):
                set_in_progress(bugtask, launchpad,
                                args.uploader, args.change_url)
        else:
            series = args.branch.rsplit('/', 1)[-1]

        if series:
            # Look for a related task matching the series.
            for reltask in bugtask.related_tasks:
                if (reltask.bug_target_name.endswith(series) and
                        task.needs_change('set_in_progress') and
                        reltask.status not in [u'Fix Committed',
                                               u'Fix Released']):
                    set_in_progress(reltask, launchpad,
                                    args.uploader, args.change_url)
                    break

        if args.patchset == '1' and (task.needs_change('add_comment') or
                                     task.needs_change('sidenote')):
            add_change_proposed_message(bugtask, args.change_url,
                                        args.project, args.branch,
                                        related=task.needs_change('sidenote'))


def find_bugs(launchpad, git_log, args):
    '''Find bugs referenced in the git log and return related tasks.

    Our regular expression is composed of three major parts:
    part1: Matches only at start-of-line (required). Optionally matches any
           word or hyphen separated words.
    part2: Matches the words 'bug' or 'lp' on a word boundary (required).
    part3: Matches a whole number (required).

    The following patterns will be matched properly:
    bug # 555555
    Closes-Bug: 555555
    Fixes: bug # 555555
    Resolves: bug 555555
    Partial-Bug: lp bug # 555555

    :returns: an iterable containing Task objects.
    '''

    project = args.project

    if p.is_no_launchpad_bugs(project):
        return []

    projects = p.project_to_groups(project)

    part1 = r'^[\t ]*(?P<prefix>[-\w]+)?[\s:]*'
    part2 = r'(?:\b(?:bug|lp)\b[\s#:]*)+'
    part3 = r'(?P<bug_number>\d+)\s*?$'
    regexp = part1 + part2 + part3
    matches = re.finditer(regexp, git_log, flags=re.I | re.M)

    # Extract unique bug tasks and associated prefixes.
    bugtasks = {}
    for match in matches:
        prefix = match.group('prefix')
        bug_num = match.group('bug_number')
        if bug_num not in bugtasks:
            try:
                lp_bug = launchpad.bugs[bug_num]
                for lp_task in lp_bug.bug_tasks:
                    if lp_task.bug_target_name in projects:
                        bugtasks[bug_num] = Task(lp_task, prefix)
                        break
            except KeyError:
                # Unknown bug.
                pass

    return bugtasks.values()


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
    # change-abandoned
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

    args = parser.parse_args()

    # Connect to Launchpad.
    lpconn = launchpad.Launchpad.login_with(
        'Gerrit User Sync', uris.LPNET_SERVICE_ROOT, GERRIT_CACHE_DIR,
        credentials_file=GERRIT_CREDENTIALS, version='devel')

    # Get git log.
    git_log = extract_git_log(args)

    # Process tasks found in git log.
    for task in find_bugs(lpconn, git_log, args):
        process_bugtask(lpconn, task, git_log, args)


if __name__ == "__main__":
    main()
