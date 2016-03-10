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
import ConfigParser
import logging
import os
import re
import shlex
import subprocess
import tempfile
import time

import gerritlib.gerrit
import github

import jeepyb.gerritdb
import jeepyb.log as l
import jeepyb.utils as u

registry = u.ProjectsRegistry()

log = logging.getLogger("manage_projects")

# Gerrit system groups as defined:
# https://review.openstack.org/Documentation/access-control.html#system_groups
# Need to set Gerrit system group's uuid to the format it expects.
GERRIT_SYSTEM_GROUPS = {
    'Anonymous Users': 'global:Anonymous-Users',
    'Project Owners': 'global:Project-Owners',
    'Registered Users': 'global:Registered-Users',
    'Change Owner': 'global:Change-Owner',
}


class FetchConfigException(Exception):
    pass


class CopyACLException(Exception):
    pass


class CreateGroupException(Exception):
    pass


def run_command(cmd, status=False, env=None):
    env = env or {}
    cmd_list = shlex.split(str(cmd))
    newenv = os.environ
    newenv.update(env)
    log.info("Executing command: %s" % " ".join(cmd_list))
    p = subprocess.Popen(cmd_list, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, env=newenv)
    (out, nothing) = p.communicate()
    log.debug("Return code: %s" % p.returncode)
    log.debug("Command said: %s" % out.strip())
    if status:
        return (p.returncode, out.strip())
    return out.strip()


def run_command_status(cmd, env=None):
    env = env or {}
    return run_command(cmd, True, env)


def git_command(repo_dir, sub_cmd, env=None):
    env = env or {}
    git_dir = os.path.join(repo_dir, '.git')
    cmd = "git --git-dir=%s --work-tree=%s %s" % (git_dir, repo_dir, sub_cmd)
    status, _ = run_command(cmd, True, env)
    return status


def git_command_output(repo_dir, sub_cmd, env=None):
    env = env or {}
    git_dir = os.path.join(repo_dir, '.git')
    cmd = "git --git-dir=%s --work-tree=%s %s" % (git_dir, repo_dir, sub_cmd)
    status, out = run_command(cmd, True, env)
    return (status, out)


def fetch_config(project, remote_url, repo_path, env=None):
    env = env or {}
    # Poll for refs/meta/config as gerrit may not have written it out for
    # us yet.
    for x in range(10):
        status = git_command(repo_path, "fetch %s +refs/meta/config:"
                             "refs/remotes/gerrit-meta/config" %
                             remote_url, env)
        if status == 0:
            break
        else:
            log.debug("Failed to fetch refs/meta/config for project: %s" %
                      project)
            time.sleep(2)
    if status != 0:
        log.error("Failed to fetch refs/meta/config for project: %s" % project)
        raise FetchConfigException()

    # Poll for project.config as gerrit may not have committed an empty
    # one yet.
    output = ""
    for x in range(10):
        status = git_command(repo_path, "remote update --prune", env)
        if status != 0:
            log.error("Failed to update remote: %s" % remote_url)
            time.sleep(2)
            continue
        else:
            status, output = git_command_output(
                repo_path, "ls-files --with-tree=remotes/gerrit-meta/config "
                "project.config", env)
        if output.strip() != "project.config" or status != 0:
            log.debug("Failed to find project.config for project: %s" %
                      project)
            time.sleep(2)
        else:
            break
    if output.strip() != "project.config" or status != 0:
        log.error("Failed to find project.config for project: %s" % project)
        raise FetchConfigException()

    # Because the following fails if executed more than once you should only
    # run fetch_config once in each repo.
    status = git_command(repo_path, "checkout -B config "
                         "remotes/gerrit-meta/config")
    if status != 0:
        log.error("Failed to checkout config for project: %s" % project)
        raise FetchConfigException()


def copy_acl_config(project, repo_path, acl_config):
    if not os.path.exists(acl_config):
        raise CopyACLException()

    acl_dest = os.path.join(repo_path, "project.config")
    status, _ = run_command("cp %s %s" %
                            (acl_config, acl_dest), status=True)
    if status != 0:
        raise CopyACLException()

    status = git_command(repo_path, "diff --quiet")
    return status != 0


def push_acl_config(project, remote_url, repo_path, gitid, env=None):
    env = env or {}
    cmd = "commit -a -m'Update project config.' --author='%s'" % gitid
    status = git_command(repo_path, cmd)
    if status != 0:
        log.error("Failed to commit config for project: %s" % project)
        return False
    status, out = git_command_output(repo_path,
                                     "push %s HEAD:refs/meta/config" %
                                     remote_url, env)
    if status != 0:
        log.error("Failed to push config for project: %s" % project)
        return False
    return True


def _get_group_uuid(group):
    """
    Gerrit keeps internal user groups in the DB while it keeps systems
    groups in All-Projects groups file (in refs/meta/config).  This
    will only get the UUIDs for internal user groups.

    Note: 'Administrators', 'Non-Interactive Users' and all other custom
    groups in Gerrit are defined as internal user groups.

    Wait for up to 10 seconds for the group to be created in the DB.
    """
    query = "SELECT group_uuid FROM account_groups WHERE name = %s"
    con = jeepyb.gerritdb.connect()
    for x in range(10):
        cursor = con.cursor()
        cursor.execute(query, (group,))
        data = cursor.fetchone()
        cursor.close()
        con.commit()
        if data:
            return data[0]
        time.sleep(1)
    return None


def get_group_uuid(gerrit, group):
    uuid = _get_group_uuid(group)
    if uuid:
        return uuid
    if group in GERRIT_SYSTEM_GROUPS:
        return GERRIT_SYSTEM_GROUPS[group]
    gerrit.createGroup(group)
    uuid = _get_group_uuid(group)
    if uuid:
        return uuid
    return None


def create_groups_file(project, gerrit, repo_path):
    acl_config = os.path.join(repo_path, "project.config")
    group_file = os.path.join(repo_path, "groups")
    uuids = {}
    for line in open(acl_config, 'r'):
        r = re.match(r'^.*\sgroup\s+(.*)$', line)
        if r:
            group = r.group(1)
            if group in uuids.keys():
                continue
            uuid = get_group_uuid(gerrit, group)
            if uuid:
                uuids[group] = uuid
            else:
                log.error("Unable to get UUID for group %s." % group)
                raise CreateGroupException()
    if uuids:
        with open(group_file, 'w') as fp:
            for group, uuid in uuids.items():
                fp.write("%s\t%s\n" % (uuid, group))
        status = git_command(repo_path, "add groups")
        if status != 0:
            log.error("Failed to add groups file for project: %s" % project)
            raise CreateGroupException()


def make_ssh_wrapper(gerrit_user, gerrit_key):
    (fd, name) = tempfile.mkstemp(text=True)
    os.write(fd, '#!/bin/bash\n')
    os.write(fd,
             'ssh -i %s -l %s -o "StrictHostKeyChecking no" $@\n' %
             (gerrit_key, gerrit_user))
    os.close(fd)
    os.chmod(name, 0o755)
    return dict(GIT_SSH=name)


def create_github_project(
        default_has_issues, default_has_downloads, default_has_wiki,
        github_secure_config, options, project, description, homepage):
    created = False
    has_issues = 'has-issues' in options or default_has_issues
    has_downloads = 'has-downloads' in options or default_has_downloads
    has_wiki = 'has-wiki' in options or default_has_wiki

    secure_config = ConfigParser.ConfigParser()
    secure_config.read(github_secure_config)

    if secure_config.has_option("github", "oauth_token"):
        ghub = github.Github(secure_config.get("github", "oauth_token"))
    else:
        ghub = github.Github(secure_config.get("github", "username"),
                             secure_config.get("github", "password"))
    orgs = ghub.get_user().get_orgs()
    orgs_dict = dict(zip([o.login.lower() for o in orgs], orgs))

    # Find the project's repo
    project_split = project.split('/', 1)
    org_name = project_split[0]
    if len(project_split) > 1:
        repo_name = project_split[1]
    else:
        repo_name = project

    try:
        org = orgs_dict[org_name.lower()]
    except KeyError:
        # We do not have control of this github org ignore the project.
        return False
    try:
        repo = org.get_repo(repo_name)
    except github.GithubException:
        repo = org.create_repo(repo_name,
                               homepage=homepage,
                               has_issues=has_issues,
                               has_downloads=has_downloads,
                               has_wiki=has_wiki)
        if description:
            repo.edit(repo_name, description=description)
        if homepage:
            repo.edit(repo_name, homepage=homepage)
        repo.edit(repo_name, has_issues=has_issues,
                  has_downloads=has_downloads,
                  has_wiki=has_wiki)

        if 'gerrit' not in [team.name for team in repo.get_teams()]:
            teams = org.get_teams()
            teams_dict = dict(zip([t.name.lower() for t in teams], teams))
            teams_dict['gerrit'].add_to_repos(repo)
        created = True

    return created


# TODO(mordred): Inspect repo_dir:master for a description
#                override
def find_description_override(repo_path):
    return None


def make_local_copy(repo_path, project, project_list,
                    git_opts, ssh_env, upstream, GERRIT_HOST, GERRIT_PORT,
                    project_git, GERRIT_GITID):

    # Ensure that the base location exists
    if not os.path.exists(os.path.dirname(repo_path)):
        os.makedirs(os.path.dirname(repo_path))

    # Three choices
    #  - If gerrit has it, get from gerrit
    #  - If gerrit doesn't have it:
    #    - If it has an upstream, clone that
    #    - If it doesn't, create it

    # Gerrit knows about the project, clone it
    # TODO(mordred): there is a possible failure condition here
    #                we should consider 'gerrit has it' to be
    #                'gerrit repo has a master branch'
    if project in project_list:
        run_command(
            "git clone %(remote_url)s %(repo_path)s" % git_opts,
            env=ssh_env)
        if upstream:
            git_command(
                repo_path,
                "remote add -f upstream %(upstream)s" % git_opts)
        return None

    # Gerrit doesn't have it, but it has an upstream configured
    # We're probably importing it for the first time, clone
    # upstream, but then ongoing we want gerrit to ge origin
    # and upstream to be only there for ongoing tracking
    # purposes, so rename origin to upstream and add a new
    # origin remote that points at gerrit
    elif upstream:
        run_command(
            "git clone %(upstream)s %(repo_path)s" % git_opts,
            env=ssh_env)
        git_command(
            repo_path,
            "fetch origin +refs/heads/*:refs/copy/heads/*",
            env=ssh_env)
        git_command(repo_path, "remote rename origin upstream")
        git_command(
            repo_path,
            "remote add origin %(remote_url)s" % git_opts)
        return "push %s +refs/copy/heads/*:refs/heads/*"

    # Neither gerrit has it, nor does it have an upstream,
    # just create a whole new one
    else:
        run_command("git init %s" % repo_path)
        git_command(
            repo_path,
            "remote add origin %(remote_url)s" % git_opts)
        with open(os.path.join(repo_path,
                               ".gitreview"),
                  'w') as gitreview:
            gitreview.write("""[gerrit]
host=%s
port=%s
project=%s
""" % (GERRIT_HOST, GERRIT_PORT, project_git))
        git_command(repo_path, "add .gitreview")
        cmd = ("commit -a -m'Added .gitreview' --author='%s'"
               % GERRIT_GITID)
        git_command(repo_path, cmd)
        return "push %s HEAD:refs/heads/master"


def update_local_copy(repo_path, track_upstream, git_opts, ssh_env):
    # first do a clean of the branch to prevent possible
    # problems due to previous runs
    git_command(repo_path, "clean -fdx")

    has_upstream_remote = (
        'upstream' in git_command_output(repo_path, 'remote')[1])
    if track_upstream:
        # If we're configured to track upstream but the repo
        # does not have an upstream remote, add one
        if not has_upstream_remote:
            git_command(
                repo_path,
                "remote add upstream %(upstream)s" % git_opts)

        # If we're configured to track upstream, make sure that
        # the upstream URL matches the config
        else:
            git_command(
                repo_path,
                "remote set-url upstream %(upstream)s" % git_opts)

        # Now that we have any upstreams configured, fetch all of the refs
        # we might need, pruning remote branches that no longer exist
        git_command(
            repo_path, "remote update --prune", env=ssh_env)
    else:
        # If we are not tracking upstream, then we do not need
        # an upstream remote configured
        if has_upstream_remote:
            git_command(repo_path, "remote rm upstream")

    # TODO(mordred): This is here so that later we can
    # inspect the master branch for meta-info
    # Checkout master and reset to the state of origin/master
    git_command(repo_path, "checkout -B master origin/master")


def push_to_gerrit(repo_path, project, push_string, remote_url, ssh_env):
    try:
        git_command(repo_path, push_string % remote_url, env=ssh_env)
        git_command(repo_path, "push --tags %s" % remote_url, env=ssh_env)
    except Exception:
        log.exception(
            "Error pushing %s to Gerrit." % project)


def sync_upstream(repo_path, project, ssh_env, upstream_prefix):
    git_command(
        repo_path,
        "remote update upstream --prune", env=ssh_env)
    # Any branch that exists in the upstream remote, we want
    # a local branch of, optionally prefixed with the
    # upstream prefix value
    for branch in git_command_output(
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
        git_command(repo_path, "checkout -B %s %s" % (
            local_branch, branch))

    try:
        # Push all of the local branches to similarly named
        # Branches on gerrit. Also, push all of the tags
        git_command(
            repo_path,
            "push origin refs/heads/*:refs/heads/*",
            env=ssh_env)
        git_command(repo_path, 'push origin --tags', env=ssh_env)
    except Exception:
        log.exception(
            "Error pushing %s to Gerrit." % project)


def process_acls(acl_config, project, ACL_DIR, section,
                 remote_url, repo_path, ssh_env, gerrit, GERRIT_GITID):
    if not os.path.isfile(acl_config):
        return
    try:
        fetch_config(project, remote_url, repo_path, ssh_env)
        if not copy_acl_config(project, repo_path, acl_config):
            # nothing was copied, so we're done
            return
        create_groups_file(project, gerrit, repo_path)
        push_acl_config(project, remote_url, repo_path,
                        GERRIT_GITID, ssh_env)
    except Exception:
        log.exception(
            "Exception processing ACLS for %s." % project)
    finally:
        git_command(repo_path, 'reset --hard')
        git_command(repo_path, 'checkout master')
        git_command(repo_path, 'branch -D config')


def create_gerrit_project(project, project_list, gerrit):
    if project not in project_list:
        try:
            gerrit.createProject(project)
            return True
        except Exception:
            log.exception(
                "Exception creating %s in Gerrit." % project)
            raise
    return False


def create_local_mirror(local_git_dir, project_git,
                        gerrit_system_user, gerrit_system_group):

    git_mirror_path = os.path.join(local_git_dir, project_git)
    if not os.path.exists(git_mirror_path):
        (ret, output) = run_command_status(
            "git --bare init %s" % git_mirror_path)
        if ret:
            run_command("rm -rf git_mirror_path")
            raise Exception(output)
        run_command("chown -R %s:%s %s"
                    % (gerrit_system_user, gerrit_system_group,
                       git_mirror_path))


def main():
    parser = argparse.ArgumentParser(description='Manage projects')
    l.setup_logging_arguments(parser)
    parser.add_argument('--nocleanup', action='store_true',
                        help='do not remove temp directories')
    parser.add_argument('projects', metavar='project', nargs='*',
                        help='name of project(s) to process')
    args = parser.parse_args()
    l.configure_logging(args)

    default_has_github = registry.get_defaults('has-github', True)

    LOCAL_GIT_DIR = registry.get_defaults('local-git-dir', '/var/lib/git')
    JEEPYB_CACHE_DIR = registry.get_defaults('jeepyb-cache-dir',
                                             '/var/lib/jeepyb')
    ACL_DIR = registry.get_defaults('acl-dir')
    GERRIT_HOST = registry.get_defaults('gerrit-host')
    GERRIT_PORT = int(registry.get_defaults('gerrit-port', '29418'))
    GERRIT_USER = registry.get_defaults('gerrit-user')
    GERRIT_KEY = registry.get_defaults('gerrit-key')
    GERRIT_GITID = registry.get_defaults('gerrit-committer')
    GERRIT_REPLICATE = registry.get_defaults('gerrit-replicate', True)
    GERRIT_OS_SYSTEM_USER = registry.get_defaults('gerrit-system-user',
                                                  'gerrit2')
    GERRIT_OS_SYSTEM_GROUP = registry.get_defaults('gerrit-system-group',
                                                   'gerrit2')
    DEFAULT_HOMEPAGE = registry.get_defaults('homepage')
    DEFAULT_HAS_ISSUES = registry.get_defaults('has-issues', False)
    DEFAULT_HAS_DOWNLOADS = registry.get_defaults('has-downloads', False)
    DEFAULT_HAS_WIKI = registry.get_defaults('has-wiki', False)
    GITHUB_SECURE_CONFIG = registry.get_defaults(
        'github-config',
        '/etc/github/github-projects.secure.config')

    gerrit = gerritlib.gerrit.Gerrit(GERRIT_HOST,
                                     GERRIT_USER,
                                     GERRIT_PORT,
                                     GERRIT_KEY)
    project_list = gerrit.listProjects()
    ssh_env = make_ssh_wrapper(GERRIT_USER, GERRIT_KEY)
    try:

        for section in registry.configs_list:
            project = section['project']
            if args.projects and project not in args.projects:
                continue

            try:
                log.info("Processing project: %s" % project)

                # Figure out all of the options
                options = section.get('options', dict())
                description = section.get('description', None)
                homepage = section.get('homepage', DEFAULT_HOMEPAGE)
                upstream = section.get('upstream', None)
                upstream_prefix = section.get('upstream-prefix', None)
                track_upstream = 'track-upstream' in options
                repo_path = os.path.join(JEEPYB_CACHE_DIR, project)

                # If this project doesn't want to use gerrit, exit cleanly.
                if 'no-gerrit' in options:
                    continue

                project_git = "%s.git" % project
                remote_url = "ssh://%s:%s/%s" % (
                    GERRIT_HOST,
                    GERRIT_PORT,
                    project)
                git_opts = dict(upstream=upstream,
                                repo_path=repo_path,
                                remote_url=remote_url)
                acl_config = section.get(
                    'acl-config',
                    '%s.config' % os.path.join(ACL_DIR, project))

                # Create the project in Gerrit first, since it will fail
                # spectacularly if its project directory or local replica
                # already exist on disk
                project_created = create_gerrit_project(
                    project, project_list, gerrit)

                # Create the repo for the local git mirror
                create_local_mirror(
                    LOCAL_GIT_DIR, project_git,
                    GERRIT_OS_SYSTEM_USER, GERRIT_OS_SYSTEM_GROUP)

                if not os.path.exists(repo_path) or project_created:
                    # We don't have a local copy already, get one

                    # Make Local repo
                    push_string = make_local_copy(
                        repo_path, project, project_list,
                        git_opts, ssh_env, upstream, GERRIT_HOST, GERRIT_PORT,
                        project_git, GERRIT_GITID)
                else:
                    # We do have a local copy of it already, make sure it's
                    # in shape to have work done.
                    update_local_copy(
                        repo_path, track_upstream, git_opts, ssh_env)

                description = (
                    find_description_override(repo_path) or description)

                if project_created:
                    push_to_gerrit(
                        repo_path, project, push_string, remote_url, ssh_env)
                    if GERRIT_REPLICATE:
                        gerrit.replicate(project)

                # If we're configured to track upstream, make sure we have
                # upstream's refs, and then push them to the appropriate
                # branches in gerrit
                if track_upstream:
                    sync_upstream(repo_path, project, ssh_env, upstream_prefix)

                if acl_config:
                    process_acls(
                        acl_config, project, ACL_DIR, section,
                        remote_url, repo_path, ssh_env, gerrit, GERRIT_GITID)

                if 'has-github' in options or default_has_github:
                    created = create_github_project(
                        DEFAULT_HAS_ISSUES, DEFAULT_HAS_DOWNLOADS,
                        DEFAULT_HAS_WIKI, GITHUB_SECURE_CONFIG,
                        options, project, description, homepage)
                    if created and GERRIT_REPLICATE:
                        gerrit.replicate(project)

            except Exception:
                log.exception(
                    "Problems creating %s, moving on." % project)
                continue
    finally:
        os.unlink(ssh_env['GIT_SSH'])

if __name__ == "__main__":
    main()
