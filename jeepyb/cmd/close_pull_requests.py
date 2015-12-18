#! /usr/bin/env python
# Copyright (C) 2011 OpenStack, LLC.
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

# Github pull requests closer reads a project config file called projects.yaml
# It should look like:

# - homepage: http://openstack.org
#   team-id: 153703
#   has-wiki: False
#   has-issues: False
#   has-downloads: False
# ---
# - project: PROJECT_NAME
#   options:
#   - has-pull-requests

# Github authentication information is read from github.secure.config,
# which should look like:

# [github]
# username = GITHUB_USERNAME
# password = GITHUB_PASSWORD
#
# or
#
# [github]
# oauth_token = GITHUB_OAUTH_TOKEN

import argparse
import ConfigParser
import github
import logging
import os

import jeepyb.log as l
import jeepyb.projects as p
import jeepyb.utils as u

MESSAGE = """Thank you for contributing to %(project)s!

%(project)s uses Gerrit for code review.

If you have never contributed to OpenStack before make sure you have read the
getting started documentation:
http://docs.openstack.org/infra/manual/developers.html#getting-started

Otherwise please visit
http://docs.openstack.org/infra/manual/developers.html#development-workflow
and follow the instructions there to upload your change to Gerrit.
"""

log = logging.getLogger("close_pull_requests")


def main():

    parser = argparse.ArgumentParser()
    l.setup_logging_arguments(parser)
    parser.add_argument('--message-file', dest='message_file', default=None,
                        help='The close pull request message')

    args = parser.parse_args()
    l.configure_logging(args)

    if args.message_file:
        try:
            with open(args.message_file, 'r') as _file:
                pull_request_text = _file.read()
        except (OSError, IOError):
            log.exception("Could not open close pull request message file")
            raise
    else:
        pull_request_text = MESSAGE

    GITHUB_SECURE_CONFIG = os.environ.get('GITHUB_SECURE_CONFIG',
                                          '/etc/github/github.secure.config')

    secure_config = ConfigParser.ConfigParser()
    secure_config.read(GITHUB_SECURE_CONFIG)
    registry = u.ProjectsRegistry()

    if secure_config.has_option("github", "oauth_token"):
        ghub = github.Github(secure_config.get("github", "oauth_token"))
    else:
        ghub = github.Github(secure_config.get("github", "username"),
                             secure_config.get("github", "password"))

    orgs = ghub.get_user().get_orgs()
    orgs_dict = dict(zip([o.login.lower() for o in orgs], orgs))
    for section in registry.configs_list:
        project = section['project']

        # Make sure we're using GitHub for this project:
        if not p.has_github(project):
            continue

        # Make sure we're supposed to close pull requests for this project:
        if 'options' in section and 'has-pull-requests' in section['options']:
            continue

        # Find the project's repo
        project_split = project.split('/', 1)

        # Handle errors in case the repo or the organization doesn't exists
        try:
            if len(project_split) > 1:
                org = orgs_dict[project_split[0].lower()]
                repo = org.get_repo(project_split[1])
            else:
                repo = ghub.get_user().get_repo(project)
        except (KeyError, github.GithubException):
            log.exception("Could not find project %s on GitHub." % project)
            continue

        # Close each pull request
        pull_requests = repo.get_pulls("open")
        for req in pull_requests:
            vars = dict(project=project)
            issue_data = {"url": repo.url + "/issues/" + str(req.number)}
            issue = github.Issue.Issue(requester=req._requester,
                                       headers={},
                                       attributes=issue_data,
                                       completed=True)
            issue.create_comment(pull_request_text % vars)
            req.edit(state="closed")

if __name__ == "__main__":
    main()
