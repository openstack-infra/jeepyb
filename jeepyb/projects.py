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
  groups:
    - awesome-group
  options:
    - delay-release
    - no-launchpad-bugs
    - no-launchpad-blueprints
"""

import ConfigParser

import jeepyb.utils as u


registry = u.ProjectsRegistry()


def project_to_groups(project_full_name):
    return registry[project_full_name] \
        .get('groups',
             [registry[project_full_name].get('group',
                                              u.short_project_name(
                                                  project_full_name))])


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


def has_github(project_full_name):
    try:
        if not registry.defaults.get('projects', 'has-github'):
            # If the default is not to use GitHub...
            try:
                # ...then rely on the existence of a per-project option...
                return 'has-github' in registry[project_full_name]['options']
            except KeyError:
                # ...and if it's not set, then still don't use it.
                return False
    # It's okay if the global option or even the section for this don't exist.
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        pass
    # If we got this far, we either explicitly or implicitly default to use it.
    return True


def has_translations(project_full_name):
    try:
        return 'translate' in registry[project_full_name]['options']
    except KeyError:
        return False


def is_delay_release(project_full_name):
    try:
        return 'delay-release' in registry[project_full_name]['options']
    except KeyError:
        return False


def docimpact_target(project_full_name):
    return registry.get_project_item(project_full_name, 'docimpact-group',
                                     'unknown')
