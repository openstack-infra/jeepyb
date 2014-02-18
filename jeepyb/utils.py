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

import os
import yaml


def short_project_name(full_project_name):
    """Return the project part of the git repository name."""
    return full_project_name.split('/')[-1]


class ProjectsYamlRegistry(object):
    """review.projects.yaml style config file parser.

    It could be used as dict 'project name' -> 'project properties'.
    """

    def __init__(self, file_path, env_name=None, single_doc=True):
        self.file_path = file_path
        self.env_name = env_name
        self.single_doc = single_doc

        self._parse_file()

    def _parse_file(self):
        file_path = os.environ.get(self.env_name, self.file_path)
        yaml_docs = [config for config in yaml.safe_load_all(open(file_path))]
        if self.single_doc:
            configs_list = yaml_docs[0]
        else:
            configs_list = yaml_docs[1]

        configs = {}
        for section in configs_list:
            configs[section['project']] = section

        self.configs = configs

    def __getitem__(self, item):
        return self.configs[item]

    def get_project_item(self, project, item, default=None):
        if project in self.configs:
            return self.configs[project].get(item, default)
        else:
            return default
