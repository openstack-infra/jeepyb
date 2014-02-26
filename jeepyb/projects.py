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

"""
Expected review.projects.yaml format:

- project: some/project
  launchpad: awesomeproject
  description: Best project ever.
  options:
    - direct-release
    - no-launchpad-bugs
    - no-launchpad-blueprints
"""

import jeepyb.utils as u


registry = u.ProjectsYamlRegistry('/home/gerrit2/projects.yaml',
                                  'PROJECTS_YAML')


def project_to_group(project_full_name):
    return registry[project_full_name].get(
        'group', registry[project_full_name].get(
            'launchpad', u.short_project_name(project_full_name)))


def _is_no_launchpad(project_full_name, obj_type):
    try:
        return ('no-launchpad-' + obj_type
                in registry[project_full_name]['options'])
    except KeyError:
        return False


def is_no_launchpad_bugs(project_full_name):
    return _is_no_launchpad(project_full_name, 'bugs')


def is_no_launchpad_blueprints(project_full_name):
    return _is_no_launchpad(project_full_name, 'blueprints')


def is_direct_release(project_full_name):
    try:
        return 'direct-release' in registry[project_full_name]['options']
    except KeyError:
        return False


def docimpact_target(project_full_name):
    return registry.get_project_item(project_full_name, 'docimpact-group',
                                     'unknown')
