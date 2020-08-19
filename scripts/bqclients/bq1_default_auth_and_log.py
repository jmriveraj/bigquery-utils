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

""" 1) Most basic script to query BigQuery, using default authentication and logging """

from google.cloud import bigquery
import logging
import traceback
import sys

__author__ = 'nikunjbhartia@google.com (Nikunj Bhartia)'

_QUERY = None
Logger = None
BigqueryClient = None

def init_logger():
    """Initializing default python logger"""
    global Logger
    logger_name = "bqclient"
    Logger = logging.getLogger(logger_name)
    logging.basicConfig(level=logging.INFO)


def init_bigquery_client():
    """Iniitializing Bigquery Client using env variable for authentication"""
    global BigqueryClient

    # Takes credential file path from the env varibale : GOOGLE_APPLICATION_CREDENTIALS pointing to credential file
    # More details Google's Application Default Credentials Strategy(ADC) strategy : https://cloud.google.com/docs/authentication/production
    BigqueryClient = bigquery.Client()


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
    Logger.info("Input Query String : %s"%(_QUERY))


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
        Logger.error("Exception during query execution %s" %(traceback.format_exc()))
        raise
    return exit_code


def process_query_results(query_job):
    """ Modify to process the results as per requirement. Below example prints every row"""

     # This is Blocking Call and bails out until timeout is exceeded or query returns successfully
    results = query_job.result()
    for row in results:
        # row._class_ = google.cloud.bigquery.table.Row
        # Eg: row => Row(('https://stackoverflow.com/questions/22879669', 48540), {'url': 0, 'view_count': 1})
        Logger.info("Url : %s, Views : %s" %(row.url, row.view_count))


if __name__ == '__main__':
    init_logger()
    init_bigquery_client()
    init_query_text()
    exit_code = run_query()
    sys.exit(exit_code)
