#! /usr/bin/env python
# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
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
#
# create_cgitrepos.py reads the project config file called projects.yaml
# and generates a cgitrepos configuration file which is then copied to
# the cgit server.
#
# It also creates the necessary top-level directories for each project
# organization (openstack, stackforge, etc)

import os
import subprocess

import jeepyb.utils as u


PROJECTS_YAML = os.environ.get('PROJECTS_YAML', '/home/cgit/projects.yaml')
CGIT_REPOS = os.environ.get('CGIT_REPOS', '/etc/cgitrepos')
REPO_PATH = os.environ.get('REPO_PATH', '/var/lib/git')
ALIAS_PATH = os.environ.get('REPO_PATH', '/var/lib/git-alias')
SCRATCH_SUBPATH = os.environ.get('SCRATCH_SUBPATH')
SCRATCH_OWNER = os.environ.get('SCRATCH_OWNER', 'scratch')
SCRATCH_GROUP = os.environ.get('SCRATCH_GROUP', 'scratch')
CGIT_USER = os.environ.get('CGIT_USER', 'cgit')
CGIT_GROUP = os.environ.get('CGIT_GROUP', 'cgit')
DEFAULT_ORG = os.environ.get('DEFAULT_ORG', None)


def clean_string(string):
    """Scrub out characters that with break cgit.

    cgit can't handle newlines in many of its fields, so strip them
    out.

    """
    return string.replace('\n', ' ').replace('\r', '')


def main():
    registry = u.ProjectsRegistry(PROJECTS_YAML)
    gitorgs = {}
    names = set()
    # site -> [(path, project, description)]
    alias_sites = {}
    for entry in registry.configs_list:
        project = entry['project']
        if '/' in project:
            (org, name) = project.split('/')
        else:
            if DEFAULT_ORG is None:
                raise RuntimeError('No org specified for project %s and no'
                                   'DEFAULT_ORG is set.' % project)
            (org, name) = (DEFAULT_ORG, project)
        description = entry.get('description', name)
        assert project not in names
        names.add(project)
        gitorgs.setdefault(org, []).append((name, description))
        if 'cgit-alias' in entry:
            alias_site = entry['cgit-alias']['site']
            alias_path = entry['cgit-alias']['path']
            alias_sites.setdefault(alias_site, []).append(
                (alias_path, project, description))
    if SCRATCH_SUBPATH:
        assert SCRATCH_SUBPATH not in gitorgs
        scratch_path = os.path.join(REPO_PATH, SCRATCH_SUBPATH)
        for org in gitorgs:
            scratch_dir = os.path.join(scratch_path, org)
            if not os.path.isdir(scratch_dir):
                os.makedirs(scratch_dir)
            projects = gitorgs[org]
            for (name, description) in projects:
                scratch_repo = "%s.git" % os.path.join(scratch_dir, name)
                subprocess.call(['git', 'init', '--bare', scratch_repo])
                subprocess.call(['chown', '-R', '%s:%s'
                                 % (SCRATCH_OWNER, SCRATCH_GROUP),
                                 scratch_repo])
    for org in gitorgs:
        if not os.path.isdir('%s/%s' % (REPO_PATH, org)):
            os.makedirs('%s/%s' % (REPO_PATH, org))
    with open(CGIT_REPOS, 'w') as cgit_file:
        cgit_file.write('# Autogenerated by create_cgitrepos.py\n')
        for org in sorted(gitorgs):
            cgit_file.write('\n')
            cgit_file.write('section=%s\n' % (org))
            org_dir = os.path.join(REPO_PATH, org)
            projects = gitorgs[org]
            projects.sort()
            for (name, description) in projects:
                project_repo = "%s.git" % os.path.join(org_dir, name)
                cgit_file.write('\n')
                cgit_file.write('repo.url=%s/%s\n' % (org, name))
                cgit_file.write('repo.path=%s/\n' % (project_repo))
                cgit_file.write(
                    'repo.desc=%s\n' % (clean_string(description)))
                if not os.path.exists(project_repo):
                    subprocess.call(['git', 'init', '--bare', project_repo])
                    subprocess.call(['chown', '-R', '%s:%s'
                                     % (CGIT_USER, CGIT_GROUP), project_repo])
    for alias_site, aliases in alias_sites.items():
        # Create all the symlinks for this alias site first
        for (alias_path, project, description) in aliases:
            alias_site_root = os.path.join(ALIAS_PATH, alias_site)
            if not os.path.exists(alias_site_root):
                os.makedirs(alias_site_root)
            alias_link_path = os.path.join(alias_site_root, alias_path)
            alias_link_path += '.git'
            alias_repo_path = os.path.join(REPO_PATH, project)
            alias_repo_path += '.git'
            if not os.path.exists(alias_link_path):
                os.symlink(alias_repo_path, alias_link_path)
        # Then create the cgit repo config
        cgit_path = CGIT_REPOS + '_' + alias_site
        with open(cgit_path, 'w') as cgit_file:
            cgit_file.write('# Autogenerated by create_cgitrepos.py\n')
            for (alias_path, project, description) in aliases:
                project_repo = "%s.git" % os.path.join(REPO_PATH, project)
                cgit_file.write('\n')
                cgit_file.write('repo.url=%s\n' % (alias_path,))
                cgit_file.write('repo.path=%s/\n' % (project_repo,))
                cgit_file.write(
                    'repo.desc=%s\n' % (clean_string(description)))


if __name__ == "__main__":
    main()
