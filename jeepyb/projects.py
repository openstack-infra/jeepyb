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


def git2lp(project_full_name):
    try:
        return registry[project_full_name]['launchpad']
    except KeyError:
        return _hardcoded_git2lp(project_full_name)
        # return u.short_project_name(project_full_name)


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
        direct = 'direct-release' in registry[project_full_name]['options']
        # return ...
    except KeyError:
        direct = False
        # return False

    return direct or _hardcoded_is_direct_release(project_full_name)


# The following functions should be deleted when projects.yaml will be updated

def _hardcoded_is_direct_release(project_full_name):
    """Test against a list of projects who directly release changes.

    This function should be removed when projects.yaml will be updated.
    To specify direct_release you just need add option 'direct_relese' to your
    project declaration in projects.yaml

    Example:
        - project: some/project
          options:
            - direct-release
          description: Best project ever.
    """
    return project_full_name in [
        'openstack/openstack-manuals',
        'openstack/api-site',
        'openstack/tripleo-incubator',
        'openstack/tempest',
        'openstack-dev/devstack',
        'openstack-infra/askbot-theme',
        'openstack-infra/config',
        'openstack-infra/devstack-gate',
        'openstack-infra/gerrit',
        'openstack-infra/gerritbot',
        'openstack-infra/gerritlib',
        'openstack-infra/gitdm',
        'openstack-infra/lodgeit',
        'openstack-infra/meetbot',
        'openstack-infra/nose-html-output',
        'openstack-infra/publications',
        'openstack-infra/reviewday',
        'openstack-infra/statusbot',
        'stackforge/cookbook-openstack-block-storage',
        'stackforge/cookbook-openstack-common',
        'stackforge/cookbook-openstack-compute',
        'stackforge/cookbook-openstack-dashboard',
        'stackforge/cookbook-openstack-identity',
        'stackforge/cookbook-openstack-image',
        'stackforge/cookbook-openstack-metering',
        'stackforge/cookbook-openstack-network',
        'stackforge/cookbook-openstack-object-storage',
        'stackforge/cookbook-openstack-ops-database',
        'stackforge/cookbook-openstack-ops-messaging',
        'stackforge/cookbook-openstack-orchestration',
        'stackforge/openstack-chef-repo',
        'stackforge/tripleo-heat-templates',
        'stackforge/tripleo-image-elements',
    ]


def _hardcoded_git2lp(project_full_name):
    """Convert Git repo name to Launchpad project.

    This function should be removed when projects.yaml will be updated.
    To specify launchpad project name you just need add parameter 'lp' to your
    project declaration in projects.yaml

    Example:
        - project: some/project
          launchpad: awesomeproject
          description: Best project ever.
    """

    project_map = {
        'openstack/api-site': 'openstack-api-site',
        'openstack/identity-api': 'openstack-api-site',
        'openstack/object-api': 'openstack-api-site',
        'openstack/volume-api': 'openstack-api-site',
        'openstack/netconn-api': 'openstack-api-site',
        'openstack/compute-api': 'openstack-api-site',
        'openstack/image-api': 'openstack-api-site',
        'openstack/database-api': 'openstack-api-site',
        'openstack/quantum': 'neutron',
        'openstack/python-quantumclient': 'python-neutronclient',
        'openstack/oslo-incubator': 'oslo',
        'openstack/tripleo-incubator': 'tripleo',
        'openstack/django_openstack_auth': 'django-openstack-auth',
        'openstack-infra/askbot-theme': 'openstack-ci',
        'openstack-infra/config': 'openstack-ci',
        'openstack-infra/devstack-gate': 'openstack-ci',
        'openstack-infra/gear': 'openstack-ci',
        'openstack-infra/gerrit': 'openstack-ci',
        'openstack-infra/gerritbot': 'openstack-ci',
        'openstack-infra/gerritlib': 'openstack-ci',
        'openstack-infra/gitdm': 'openstack-ci',
        'openstack-infra/jeepyb': 'openstack-ci',
        'openstack-infra/jenkins-job-builder': 'openstack-ci',
        'openstack-infra/lodgeit': 'openstack-ci',
        'openstack-infra/meetbot': 'openstack-ci',
        'openstack-infra/nose-html-output': 'openstack-ci',
        'openstack-infra/publications': 'openstack-ci',
        'openstack-infra/puppet-apparmor': 'openstack-ci',
        'openstack-infra/puppet-dashboard': 'openstack-ci',
        'openstack-infra/puppet-vcsrepo': 'openstack-ci',
        'openstack-infra/reviewday': 'openstack-ci',
        'openstack-infra/statusbot': 'openstack-ci',
        'openstack-infra/zmq-event-publisher': 'openstack-ci',
        'stackforge/cookbook-openstack-block-storage': 'openstack-chef',
        'stackforge/cookbook-openstack-common': 'openstack-chef',
        'stackforge/cookbook-openstack-compute': 'openstack-chef',
        'stackforge/cookbook-openstack-dashboard': 'openstack-chef',
        'stackforge/cookbook-openstack-identity': 'openstack-chef',
        'stackforge/cookbook-openstack-image': 'openstack-chef',
        'stackforge/cookbook-openstack-metering': 'openstack-chef',
        'stackforge/cookbook-openstack-network': 'openstack-chef',
        'stackforge/cookbook-openstack-object-storage': 'openstack-chef',
        'stackforge/cookbook-openstack-ops-database': 'openstack-chef',
        'stackforge/cookbook-openstack-ops-messaging': 'openstack-chef',
        'stackforge/cookbook-openstack-orchestration': 'openstack-chef',
        'stackforge/openstack-chef-repo': 'openstack-chef',
        'stackforge/puppet-openstack_dev_env': 'puppet-openstack',
        'stackforge/puppet-quantum': 'puppet-neutron',
        'stackforge/tripleo-heat-templates': 'tripleo',
        'stackforge/tripleo-image-elements': 'tripleo',
        'stackforge/savanna': 'savanna',
        'stackforge/savanna-dashboard': 'savanna',
        'stackforge/savanna-extra': 'savanna',
        'stackforge/savanna-image-elements': 'savanna',
        'stackforge/python-savannaclient': 'savanna',
        'stackforge/puppet-savanna': 'savanna'
    }
    return project_map.get(project_full_name,
                           u.short_project_name(project_full_name))
