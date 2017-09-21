# Copyright (c) 2013 Mirantis.
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

import ConfigParser
import logging
import os
import shlex
import subprocess
import tempfile
import yaml

PROJECTS_INI = os.environ.get('PROJECTS_INI', '/home/gerrit2/projects.ini')
PROJECTS_YAML = os.environ.get('PROJECTS_YAML', '/home/gerrit2/projects.yaml')

log = logging.getLogger("jeepyb.utils")


def is_retired(entry):
    """Is a project retired"""
    if entry.get('acl-config', '').endswith('/retired.config'):
        return True
    project = entry['project']
    if '/' in project:
        (org, name) = project.split('/')
        if org.endswith('-attic'):
            return True
    return False


def short_project_name(full_project_name):
    """Return the project part of the git repository name."""
    return full_project_name.split('/')[-1]


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


def make_ssh_wrapper(gerrit_user, gerrit_key):
    (fd, name) = tempfile.mkstemp(text=True)
    os.write(fd, '#!/bin/bash\n')
    os.write(fd,
             'ssh -i %s -l %s -o "StrictHostKeyChecking no" $@\n' %
             (gerrit_key, gerrit_user))
    os.close(fd)
    os.chmod(name, 0o755)
    return dict(GIT_SSH=name)


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
        try:
            run_command(
                "git clone %(remote_url)s %(repo_path)s" % git_opts,
                env=ssh_env)
            if upstream:
                git_command(
                    repo_path,
                    "remote add -f upstream %(upstream)s" % git_opts)
            return None
        except Exception:
            # If the clone fails, then we need to clone from the upstream
            # source
            pass

    # Gerrit doesn't have it, but it has an upstream configured
    # We're probably importing it for the first time, clone
    # upstream, but then ongoing we want gerrit to ge origin
    # and upstream to be only there for ongoing tracking
    # purposes, so rename origin to upstream and add a new
    # origin remote that points at gerrit
    if upstream:
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


def fsck_repo(repo_path):
    rc, out = git_command_output(repo_path, 'fsck --full')
    # Check for non zero return code or warnings which should
    # be treated as errors. In this case zeroPaddedFilemodes
    # will not be accepted by Gerrit/jgit but are accepted by C git.
    if rc != 0 or 'zeroPaddedFilemode' in out:
        log.error('git fsck of %s failed:\n%s' % (repo_path, out))
        raise Exception('git fsck failed not importing')


class ProjectsRegistry(object):
    """read config from ini or yaml file.

    It could be used as dict 'project name' -> 'project properties'.
    """
    def __init__(self, yaml_file=PROJECTS_YAML, single_doc=True):
        self.yaml_doc = [c for c in yaml.safe_load_all(open(yaml_file))]
        self.single_doc = single_doc

        self._configs_list = []
        self.defaults = {}
        self._parse_file()

    def _parse_file(self):
        if self.single_doc:
            self._configs_list = self.yaml_doc[0]
        else:
            self._configs_list = self.yaml_doc[1]

        if os.path.exists(PROJECTS_INI):
            self.defaults = ConfigParser.ConfigParser()
            self.defaults.read(PROJECTS_INI)
        else:
            try:
                self.defaults = self.yaml_doc[0][0]
            except IndexError:
                pass

        configs = {}
        for section in self._configs_list:
            configs[section['project']] = section

        self.configs = configs

    def __getitem__(self, item):
        return self.configs[item]

    def get_project_item(self, project, item, default=None):
        if project in self.configs:
            return self.configs[project].get(item, default)
        else:
            return default

    def get(self, item, default=None):
        return self.configs.get(item, default)

    def get_defaults(self, item, default=None):
        if os.path.exists(PROJECTS_INI):
            section = 'projects'
            if self.defaults.has_option(section, item):
                if type(default) == bool:
                    return self.defaults.getboolean(section, item)
                else:
                    return self.defaults.get(section, item)
            return default
        else:
            return self.defaults.get(item, default)

    @property
    def configs_list(self):
        return [entry for entry in self._configs_list if not is_retired(entry)]
