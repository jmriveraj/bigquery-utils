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

"""4) Script to query Bigquery, with structured json logging support in stdout,
      improved query result handling and added meta information for log lines.
"""

from google.cloud import bigquery
from google.oauth2 import service_account
from datetime import datetime
import logging
import traceback
import sys
import json

__author__ = 'nikunjbhartia@google.com (Nikunj Bhartia)'

_QUERY = None
Logger = None
BigqueryClient = None


class CustomJsonFormatter(logging.Formatter):
    """Custom Log formatter for supporting structured logging.

    Args:
        message : Log text
        extraAgrs : [Optional] A dictionary of extra parameters to be clubbed with the final json log structure

    Returns:
        Json log structure (dict of k,v pairs) clubbed with input arguments and extra log record attributes
    """
    def format(self, record):
        # Reference : https://googleapis.dev/python/logging/latest/handlers.html
        # Note : A logRecord instance is created automatically whenever a logger logs something
        # For more info about log record attributes : https://docs.python.org/3/library/logging.html#logrecord-attributes
        log_struct = {} if record.args == () else record.args
        log_struct['logText'] = record.msg
        log_struct['filename'] = record.filename
        log_struct['funcName'] = record.funcName
        log_struct['processId'] = record.process

        # Can be used as an identifier while debugging
        log_struct['threadId'] = record.thread
        log_struct['levelName'] = record.levelname
        log_struct['eventTimestamp'] = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")

        # If we only return log_struct, we get the error TypeError: unsupported operand type(s) for +: 'dict' and 'str'
        return json.dumps(log_struct)


def init_logger():
    """Initializing the logger global variable for stdout"""
    global Logger

    logger_name = "bqclient"
    log_level = logging.DEBUG

    #Defining handler for std.out
    stdoutlog_handler = logging.StreamHandler(sys.stdout)

    # Using customJsonFormatter class for structured json logging
    stdoutlog_handler.setFormatter(CustomJsonFormatter())

    Logger = logging.getLogger(logger_name)
    Logger.addHandler(stdoutlog_handler)
    Logger.setLevel(log_level)


def init_bigquery_client():
    """Iniitializing Bigquery Client using env variable for authentication"""
    global BigqueryClient

    credfile = "credentials/service_account.json"
    cloud_platform_scope = "https://www.googleapis.com/auth/cloud-platform"

    # When your application needs access to user data, it asks Google for a particular scope of access.
    # Access tokens are associated with a scope, which limits the token's access
    # References: https://developers.google.com/drive/api/v2/about-auth
    #             https://cloud.google.com/bigquery/docs/authorization
    #             https://tools.ietf.org/html/rfc6749#section-3.3
    credentials = service_account.Credentials.from_service_account_file(
        credfile,
        scopes=[cloud_platform_scope],
    )

    #Takes credential file path from the env varibale : GOOGLE_APPLICATION_CREDENTIALS
    #More details Google's Application Default Credentials Strategy(ADC) strategy : https://cloud.google.com/docs/authentication/production
    BigqueryClient = bigquery.Client(credentials=credentials, project=credentials.project_id)


def init_query_text():
    """Initializing the query string"""
    global _QUERY

    _QUERY = """ SELECT
                  CONCAT(
                    'https://stackoverflow.com/questions/',
                    CAST(id as STRING)) as url,
                  view_count
                FROM `bigquery-public-data.stackoverflow.posts_questions`
                WHERE tags like '%google-bigquery%'
                ORDER BY view_count DESC
                LIMIT 10"""

    # Note : Now passing an extra argument with a dict. This will be appended with extra record attributes as described in the customJsonFormatter class
    Logger.info("Query fetch successful", { 'query' : _QUERY })

def run_query():
    """Runs a BigQuery SQL query in synchronous mode and print results if the query completes within a specified timeout.

    Returns:
        0 in case of success, nonzero on failure.

    Raises:
        Exception : Failure during query runtime execution
    """
    # Setting default exit code
    exit_code = 0
    try :
        Logger.debug("Executing query")
        # For synchronous call
        query_job = BigqueryClient.query(_QUERY)  #API request
        process_query_results(query_job)

    except Exception as error:
        Logger.error("Exception during query execution ", { 'exceptionInfo' : traceback.format_exc() })
        raise

    return exit_code


def process_query_results(query_job):
    """ Modify to process the results as per requirement. Below example prints every row"""

     # This is Blocking Call and bails out until timeout is exceeded or query returns successfully
    results = query_job.result()
    for row in results:
        # row._class_ = google.cloud.bigquery.table.Row
        # Eg: row => Row(('https://stackoverflow.com/questions/22879669', 48540), {'url': 0, 'view_count': 1})
        #     list(row.items()) =>  [('url', 'https://stackoverflow.com/questions/22879669'),('view_count', 48540)]
        rowdict = dict(list(row.items()))
        Logger.info("Query result for every row", { 'result' : rowdict, 'jobId' : query_job.job_id })


if __name__ == '__main__':
    init_logger()
    init_bigquery_client()
    init_query_text()
    exit_code = run_query()
    sys.exit(exit_code)
