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

import json
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

import requests


class ZanataRestService:
    def __init__(self, url, username, api_key, verify=False):
        self.url = url
        self.verify = verify
        content_type = 'application/json;charset=utf8'
        self.headers = {'Accept': content_type,
                        'Content-Type': content_type,
                        'X-Auth-User': username,
                        'X-Auth-Token': api_key}

    def _construct_url(self, url_fragment):
        return urljoin(self.url, url_fragment)

    def query(self, url_fragment):
        request_url = self._construct_url(url_fragment)
        try:
            return requests.get(request_url, verify=self.verify,
                                headers=self.headers)
        except requests.exceptions.ConnectionError:
            raise ValueError('Connection error')

    def push(self, url_fragment, data):
        request_url = self._construct_url(url_fragment)
        try:
            return requests.put(request_url, verify=self.verify,
                                headers=self.headers, data=json.dumps(data))
        except requests.exceptions.ConnectionError:
            raise ValueError('Connection error')


class TranslationProject:
    def __init__(self, rest_service, project):
        self.rest_service = rest_service
        self.project = project

    def is_registered(self):
        r = self.rest_service.query('/rest/projects/p/%s' % self.project)
        return r.status_code == 200

    def has_master(self):
        r = self.rest_service.query(
            '/rest/projects/p/%s/iterations/i/master' % self.project)
        return r.status_code == 200

    def register_project(self):
        project_data = {u'defaultType': u'Gettext', u'status': u'ACTIVE',
                        u'id': self.project, u'name': self.project,
                        u'description': self.project.title()}
        r = self.rest_service.push('/rest/projects/p/%s' % self.project,
                                   project_data)
        return r.status_code in (200, 201)

    def register_master_iteration(self):
        iteration = {u'status': u'ACTIVE', u'projectType': u'Gettext',
                     u'id': u'master'}
        r = self.rest_service.push(
            '/rest/projects/p/%s/iterations/i/master' % self.project,
            iteration)
        return r.status_code in (200, 201)

    def register(self):
        if not self.is_registered():
            if not self.register_project():
                raise ValueError('Failed to register project.')
        if not self.has_master():
            if not self.register_master_iteration():
                raise ValueError('Failed to register master iteration.')
