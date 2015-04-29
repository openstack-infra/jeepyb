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
# create_hound_config.py reads the project config file called projects.yaml
# and generates a hound configuration file.

import json
import os

import jeepyb.utils as u


PROJECTS_YAML = os.environ.get('PROJECTS_YAML', '/home/hound/projects.yaml')
GIT_SERVER = os.environ.get('GIT_BASE', 'git.openstack.org')
DATA_PATH = os.environ.get('DATA_PATH', 'data')


def main():
    registry = u.ProjectsRegistry(PROJECTS_YAML)
    projects = [entry['project'] for entry in registry.configs_list]
    repos = {}
    for project in projects:
        repos[os.path.basename(project)] = {
            'url': "git://%(gitbase)s/%(project)s" % dict(
                gitbase=GIT_SERVER, project=project),
            'url-pattern': {
                'base-url': "http://%(gitbase)s/cgit/%(project)s"
                            "/tree/{path}{anchor}" % dict(gitbase=GIT_SERVER,
                                                          project=project),
                'anchor': '#n{line}',
            }
        }

    config = {
        "dbpath": "data",
        "repos": repos
    }
    with open('config.json', 'w') as config_file:
        config_file.write(
            json.dumps(
                config, indent=2,
                separators=(',', ': '), sort_keys=False,
                default=unicode))


if __name__ == "__main__":
    main()
