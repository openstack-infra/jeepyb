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

import logging


def setup_logging_arguments(parser):
    """Sets up logging arguments, adds -d, -l and -v to the given parser."""
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        help='verbose output')
    parser.add_argument('-d', dest='debug', action='store_true',
                        help='debug output')
    parser.add_argument('-l', dest='logfile', help='log file to use')


def configure_logging(args):
    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = logging.ERROR
    logging.basicConfig(level=level, filename=args.logfile,
                        format='%(asctime)-6s: %(name)s - %(levelname)s'
                               ' - %(message)s')
