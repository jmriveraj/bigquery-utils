#!/usr/bin/python3.7

#
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

""" Authentication using user credentials, either loading saved credentials
    from the cache or by going through the OAuth 2.0 flow in case of a cache miss """

import pydata_google_auth
import logging
import traceback
import sys
import json

__author__ = 'nikunjbhartia@google.com (Nikunj Bhartia)'

_QUERY = None
_CLIENT_ID = None
_CLIENT_SECRET = None
_PROJECT = None

# Ref :  https://developers.google.com/identity/protocols/oauth2#1.-obtain-oauth-2.0-credentials-from-the-google-api-console.
_OAUTH_SECRETS_FILE = "credentials/client_secret.json"

Logger = None

def init_logger():
    """Initializing default python logger"""
    global Logger
    logger_name = "bqclient"
    Logger = logging.getLogger(logger_name)
    logging.basicConfig(level=logging.INFO)


def init_oauth_creds():
    """ Reads the Oauth 2 credentials file and sets client secrets """
    global _CLIENT_ID, _CLIENT_SECRET, _PROJECT

    with open(_OAUTH_SECRETS_FILE) as f:
        secrets = json.load(f)

    _CLIENT_ID = secrets['installed']['client_id']
    _CLIENT_SECRET = secrets['installed']['client_secret']
    _PROJECT = secrets['installed']['project_id']


def init_oauth2_flow():
    """
    This function authenticates using user credentials, either loading saved credentials
    from the cache or by going through the OAuth 2.0 flow in case of a cache miss.

    So, you only have to do the auth flow once (until you revoke the key, need expanded scopes, or delete local cache).

    By default, credentials are cached on disk :
       - $HOME/.config/pydata/pydata_google_credentials.json
       - or $APPDATA/.config/pydata/pydata_google_credentials.json on Windows.

    Format of cached credentials :
    {
      "refresh_token": "<Refresh_Token>",
      "id_token": null,
      "token_uri": "https://accounts.google.com/o/oauth2/token",
      "client_id": "<Client_ID>",
      "client_secret": "<Client_secret>",
      "scopes": ["https://www.googleapis.com/auth/bigquery"]
    }
    """

    # Ref : https://pydata-google-auth.readthedocs.io/en/latest/api.html#pydata_google_auth.get_user_credentials
    # Note : Setting the auth_local_webserver to True thereby redirects the token to a local webserver and skipping the copy/paste
    credentials = pydata_google_auth.get_user_credentials(
        ['https://www.googleapis.com/auth/bigquery'],
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        auth_local_webserver=True
    )

    # credentials = pydata_google_auth.save_user_credentials(
    #     ['https://www.googleapis.com/auth/bigquery'],
    #     "/Users/nikunjbhartia/projects/hsbc/bigquery/bqclients/credentials/saved_cache.json",
    #     client_id=_CLIENT_ID,
    #     client_secret=_CLIENT_SECRET,
    #     use_local_webserver=True
    # )

   # BigqueryClient = bigquery.Client(project=_PROJECT, credentials=credentials)

if __name__ == '__main__':
    init_logger()
    init_oauth_creds()
    init_oauth2_flow()