#!/usr/bin/env python
# Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import logging
import os

import jeepyb.log as l
import jeepyb.projects as p
import jeepyb.translations as t
import jeepyb.utils as u

PROJECTS_YAML = os.environ.get('PROJECTS_YAML', '/home/gerrit2/projects.yaml')
ZANATA_URL = os.environ.get('ZANATA_URL')
ZANATA_USER = os.environ.get('ZANATA_USER')
ZANATA_KEY = os.environ.get('ZANATA_KEY')

log = logging.getLogger('register_zanata_projects')


def main():
    parser = argparse.ArgumentParser(description='Register projects in Zanata')
    l.setup_logging_arguments(parser)
    args = parser.parse_args()
    l.configure_logging(args)

    registry = u.ProjectsRegistry(PROJECTS_YAML)
    rest_service = t.ZanataRestService(ZANATA_URL, ZANATA_USER, ZANATA_KEY)
    log.info("Registering projects in Zanata")
    for entry in registry.configs_list:
        project = entry['project']
        if not p.has_translations(project):
            continue
        log.info("Processing project %s" % project)
        (org, name) = project.split('/')
        try:
            translation_proect = t.TranslationProject(rest_service, name)
            translation_proect.register()
        except ValueError as e:
            log.error(e)


if __name__ == "__main__":
    main()
