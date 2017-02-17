#! /usr/bin/env python
# Copyright (C) 2011 OpenStack, LLC.
# Copyright (c) 2012 Hewlett-Packard Development Company, L.P.
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

# manage_projects.py reads a config file called projects.ini
# It should look like:

# [projects]
# homepage=http://openstack.org
# gerrit-host=review.openstack.org
# local-git-dir=/var/lib/git
# gerrit-key=/home/gerrit2/review_site/etc/ssh_host_rsa_key
# gerrit-committer=Project Creator <openstack-infra@lists.openstack.org>
# gerrit-replicate=True
# has-github=True
# has-wiki=False
# has-issues=False
# has-downloads=False
# acl-dir=/home/gerrit2/acls
# acl-base=/home/gerrit2/acls/project.config
#
# manage_projects.py reads a project listing file called projects.yaml
# It should look like:
# - project: PROJECT_NAME
#   options:
#    - has-wiki
#    - has-issues
#    - has-downloads
#    - has-pull-requests
#    - track-upstream
#   homepage: Some homepage that isn't http://openstack.org
#   description: This is a great project
#   upstream: https://gerrit.googlesource.com/gerrit
#   upstream-prefix: upstream
#   acl-config: /path/to/gerrit/project.config
#   acl-append:
#     - /path/to/gerrit/project.config
#   acl-parameters:
#     project: OTHER_PROJECT_NAME

import argparse
import json
import logging
import os

import gerritlib.gerrit

import jeepyb.log as l
import jeepyb.utils as u

registry = u.ProjectsRegistry()

log = logging.getLogger("track_upstream")
orgs = None


def update_local_copy(repo_path, track_upstream, git_opts, ssh_env):
    # first do a clean of the branch to prevent possible
    # problems due to previous runs
    u.git_command(repo_path, "clean -fdx")

    has_upstream_remote = (
        'upstream' in u.git_command_output(repo_path, 'remote')[1])
    if track_upstream:
        # If we're configured to track upstream but the repo
        # does not have an upstream remote, add one
        if not has_upstream_remote:
            u.git_command(
                repo_path,
                "remote add upstream %(upstream)s" % git_opts)

        # If we're configured to track upstream, make sure that
        # the upstream URL matches the config
        else:
            u.git_command(
                repo_path,
                "remote set-url upstream %(upstream)s" % git_opts)

        # Now that we have any upstreams configured, fetch all of the refs
        # we might need, pruning remote branches that no longer exist
        u.git_command(
            repo_path, "remote update --prune", env=ssh_env)
    else:
        # If we are not tracking upstream, then we do not need
        # an upstream remote configured
        if has_upstream_remote:
            u.git_command(repo_path, "remote rm upstream")

    # TODO(mordred): This is here so that later we can
    # inspect the master branch for meta-info
    # Checkout master and reset to the state of origin/master
    u.git_command(repo_path, "checkout -B master origin/master")


def fsck_repo(repo_path):
    rc, out = u.git_command_output(repo_path, 'fsck --full')
    # Check for non zero return code or warnings which should
    # be treated as errors. In this case zeroPaddedFilemodes
    # will not be accepted by Gerrit/jgit but are accepted by C git.
    if rc != 0 or 'zeroPaddedFilemode' in out:
        log.error('git fsck of %s failed:\n%s' % (repo_path, out))
        raise Exception('git fsck failed not importing')


def push_to_gerrit(repo_path, project, push_string, remote_url, ssh_env):
    try:
        u.git_command(repo_path, push_string % remote_url, env=ssh_env)
        u.git_command(repo_path, "push --tags %s" % remote_url, env=ssh_env)
    except Exception:
        log.exception(
            "Error pushing %s to Gerrit." % project)


def sync_upstream(repo_path, project, ssh_env, upstream_prefix):
    u.git_command(
        repo_path,
        "remote update upstream --prune", env=ssh_env)
    # Any branch that exists in the upstream remote, we want
    # a local branch of, optionally prefixed with the
    # upstream prefix value
    for branch in u.git_command_output(
            repo_path, "branch -a")[1].split('\n'):
        if not branch.strip().startswith("remotes/upstream"):
            continue
        if "->" in branch:
            continue
        local_branch = branch.split()[0][len('remotes/upstream/'):]
        if upstream_prefix:
            local_branch = "%s/%s" % (
                upstream_prefix, local_branch)

        # Check out an up to date copy of the branch, so that
        # we can push it and it will get picked up below
        u.git_command(
            repo_path, "checkout -B %s %s" % (local_branch, branch))

    try:
        # Push all of the local branches to similarly named
        # Branches on gerrit. Also, push all of the tags
        u.git_command(
            repo_path,
            "push origin refs/heads/*:refs/heads/*",
            env=ssh_env)
        u.git_command(repo_path, 'push origin --tags', env=ssh_env)
    except Exception:
        log.exception(
            "Error pushing %s to Gerrit." % project)


def main():
    parser = argparse.ArgumentParser(description='Manage projects')
    l.setup_logging_arguments(parser)
    parser.add_argument('--nocleanup', action='store_true',
                        help='do not remove temp directories')
    parser.add_argument('projects', metavar='project', nargs='*',
                        help='name of project(s) to process')
    args = parser.parse_args()
    l.configure_logging(args)

    JEEPYB_CACHE_DIR = registry.get_defaults('jeepyb-cache-dir',
                                             '/var/lib/jeepyb')
    IMPORT_DIR = os.path.join(JEEPYB_CACHE_DIR, 'import')
    GERRIT_HOST = registry.get_defaults('gerrit-host')
    GERRIT_PORT = int(registry.get_defaults('gerrit-port', '29418'))
    GERRIT_USER = registry.get_defaults('gerrit-user')
    GERRIT_KEY = registry.get_defaults('gerrit-key')
    GERRIT_GITID = registry.get_defaults('gerrit-committer')

    PROJECT_CACHE_FILE = os.path.join(JEEPYB_CACHE_DIR, 'project.cache')
    project_cache = {}
    if os.path.exists(PROJECT_CACHE_FILE):
        project_cache = json.loads(open(PROJECT_CACHE_FILE, 'r').read())

    gerrit = gerritlib.gerrit.Gerrit(GERRIT_HOST,
                                     GERRIT_USER,
                                     GERRIT_PORT,
                                     GERRIT_KEY)
    project_list = gerrit.listProjects()
    ssh_env = u.make_ssh_wrapper(GERRIT_USER, GERRIT_KEY)
    try:

        for section in registry.configs_list:
            project = section['project']
            if args.projects and project not in args.projects:
                continue

            try:
                log.info("Processing project: %s" % project)

                # Figure out all of the options
                options = section.get('options', dict())
                track_upstream = 'track-upstream' in options
                if not track_upstream:
                    continue

                # If this project doesn't want to use gerrit, exit cleanly.
                if 'no-gerrit' in options:
                    continue

                upstream = section.get('upstream', None)
                upstream_prefix = section.get('upstream-prefix', None)
                repo_path = os.path.join(IMPORT_DIR, project)

                project_git = "%s.git" % project
                remote_url = "ssh://%s:%s/%s" % (
                    GERRIT_HOST,
                    GERRIT_PORT,
                    project)
                git_opts = dict(upstream=upstream,
                                repo_path=repo_path,
                                remote_url=remote_url)
                project_cache.setdefault(project, {})
                if not project_cache[project]['pushed-to-gerrit']:
                    continue

                # Make Local repo
                if not os.path.exists(repo_path):
                    u.make_local_copy(
                        repo_path, project, project_list,
                        git_opts, ssh_env, upstream, GERRIT_HOST,
                        GERRIT_PORT, project_git, GERRIT_GITID)
                else:
                    update_local_copy(
                        repo_path, track_upstream, git_opts, ssh_env)

                fsck_repo(repo_path)
                sync_upstream(repo_path, project, ssh_env, upstream_prefix)

            except Exception:
                log.exception(
                    "Problems creating %s, moving on." % project)
                continue
    finally:
        os.unlink(ssh_env['GIT_SSH'])

if __name__ == "__main__":
    main()
