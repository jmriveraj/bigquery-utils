# Copyright 2020 Google LLC.
# This software is provided as-is, without warranty or representation
# for any use or purpose.
# Your use of it is subject to your agreement with Google.

# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Configurations for Cloud Function for loading data from GCS to BigQuery.
"""
import distutils.util
import os
import re

import google.api_core.client_info
import google.cloud.exceptions

# Will wait up to this polling for errors before exiting
# This is to check if job fail quickly, not to assert it succeed.
# This may not be honored if longer than cloud function timeout.
# https://cloud.google.com/functions/docs/concepts/exec#timeout
# One might consider lowering this to 1-2 seconds to lower the
# upper bound of expected execution time to stay within the free tier.
# https://cloud.google.com/functions/pricing#free_tier
WAIT_FOR_JOB_SECONDS = int(os.getenv("WAIT_FOR_JOB_SECONDS", "5"))

DEFAULT_EXTERNAL_TABLE_DEFINITION = {
    # The default must be a self describing data format
    # because autodetecting CSV /JSON schemas is likely to not match
    # expectations / assumptions of the transformation query.
    "sourceFormat": "PARQUET",
}

# Use caution when lowering the job polling rate.
# Keep in mind that many concurrent executions of this cloud function should not
# violate the 300 concurrent requests or 100 request per second.
# https://cloud.google.com/bigquery/quotas#all_api_requests
JOB_POLL_INTERVAL_SECONDS = 1

DEFAULT_JOB_LABELS = {
    "component": "event-based-gcs-ingest",
    "cloud-function-name": os.getenv("FUNCTION_NAME"),
}

BASE_LOAD_JOB_CONFIG = {
    "sourceFormat": "CSV",
    "fieldDelimiter": ",",
    "writeDisposition": "WRITE_APPEND",
    "labels": DEFAULT_JOB_LABELS,
}

# https://cloud.google.com/bigquery/quotas#load_jobs
# 15TB per BQ load job (soft limit).
DEFAULT_MAX_BATCH_BYTES = str(15 * 10**12)

# 10,000 GCS URIs per BQ load job.
MAX_SOURCE_URIS_PER_LOAD = 10**4

SUCCESS_FILENAME = os.getenv("SUCCESS_FILENAME", "_SUCCESS")

DEFAULT_JOB_PREFIX = "gcf-ingest-"

# yapf: disable
DEFAULT_DESTINATION_REGEX = (
    r"^(?P<dataset>[\w\-\._0-9]+)/"  # dataset (required)
    r"(?P<table>[\w\-_0-9]+)/?"      # table name (required)
    r"(?P<partition>\$[0-9]+)?/?"    # partition decorator (optional)
    r"(?:"                           # [begin] yyyy/mm/dd/hh/ group (optional)
    r"(?P<yyyy>[0-9]{4})/?"          # partition year (yyyy) (optional)
    r"(?P<mm>[0-9]{2})?/?"           # partition month (mm) (optional)
    r"(?P<dd>[0-9]{2})?/?"           # partition day (dd)  (optional)
    r"(?P<hh>[0-9]{2})?/?"           # partition hour (hh) (optional)
    r")?"                            # [end]yyyy/mm/dd/hh/ group (optional)
    r"(?P<batch>[\w\-_0-9]+)?/"      # batch id (optional)
)
# yapf: enable

DESTINATION_REGEX = re.compile(
    os.getenv("DESTINATION_REGEX", DEFAULT_DESTINATION_REGEX))

CLIENT_INFO = google.api_core.client_info.ClientInfo(
    user_agent="google-pso-tool/bq-severless-loader")

# Filename used to (re)start the backfill subscriber loop.
BACKFILL_FILENAME = "_BACKFILL"

# When this file is uploaded the subscriber will start applying items in order
# off the backlog. This is meant to help scenarios where historical loads to GCS
# are parallelized but must be applied in order. One can drop a _HISTORYDONE
# file to indicate the entire history has been uploaded and it is safe to start
# applying items in the backlog in order. By default this will be empty and the
# backlog subscriber will not wait for any file and start applying the first
# items in the backlog.
START_BACKFILL_FILENAME = os.getenv("START_BACKFILL_FILENAME")

# Filenames that cause cloud function to take action.
ACTION_FILENAMES = {
    SUCCESS_FILENAME,
    BACKFILL_FILENAME,
    START_BACKFILL_FILENAME,
}

RESTART_BUFFER_SECONDS = int(os.getenv("RESTART_BUFFER_SECONDS", "30"))

ORDER_ALL_JOBS = bool(
    distutils.util.strtobool(os.getenv("ORDER_ALL_JOBS", "False")))

BQ_TRANSFORM_SQL="*.sql"