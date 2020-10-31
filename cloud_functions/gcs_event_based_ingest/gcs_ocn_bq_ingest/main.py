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
"""Background Cloud Function for loading data from GCS to BigQuery.
"""
import json
import re
from collections import deque
from datetime import timedelta
from os import getenv
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Deque, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from google.api_core.client_info import ClientInfo
from google.cloud import bigquery, storage
from google.cloud.exceptions import NotFound
from google.api_core.exceptions import PreconditionFailed

# 15TB per BQ load job.
DEFAULT_MAX_BATCH_BYTES = str(15 * 10**12)
MAX_URIS_PER_LOAD = 10**4

DEFAULT_EXTERNAL_TABLE_DEFINITION = {"sourceFormat": "PARQUET"}

DEFAULT_JOB_LABELS = {
    "component": "event-based-gcs-ingest",
    "cloud-function-name": getenv("FUNCTION_NAME"),
}

BASE_LOAD_JOB_CONFIG = {
    "sourceFormat": "CSV",
    "fieldDelimiter": "|",
    "writeDisposition": "WRITE_APPEND",
    "labels": DEFAULT_JOB_LABELS,
}

DEFAULT_DESTINATION_REGEX = r"(?P<dataset>[\w\-_0-9]+)/" \
                            r"(?P<table>[\w\-_0-9]+)/" \
                            r"?(?P<partition>\$[0-9]+)?/" \
                            r"?(?P<batch>[\w\-_0-9]+)?/"

# Will wait up to this polling for errors before exiting
# This is to check if job fail quickly, not to assert the succeed
# This may not be honored if longer than cloud function timeout
# https://cloud.google.com/functions/docs/concepts/exec#timeout
WAIT_FOR_JOB_SECONDS = 5
SUCCESS_FILENAME = getenv("SUCCESS_FILENAME", "_SUCCESS")

CLIENT_INFO = ClientInfo(user_agent="google-pso-tool/bq-severless-loader")


def main(event: Dict, context):    # pylint: disable=unused-argument
    """entry point for background cloud function for event driven GCS to
    BigQuery ingest."""
    # pylint: disable=too-many-locals
    # Set by Cloud Function Execution Environment
    # https://cloud.google.com/functions/docs/env-var
    project = getenv("GCP_PROJECT")
    destination_regex = getenv("DESTINATION_REGEX", DEFAULT_DESTINATION_REGEX)
    dest_re = re.compile(destination_regex)

    bucket_id, object_id = parse_notification(event)

    # Exit eagerly if not a success file.
    # we can improve this with pub/sub message filtering once it supports
    # a hasSuffix filter function (we can filter on hasSuffix successfile name)
    #  https://cloud.google.com/pubsub/docs/filtering
    if not object_id.endswith(f"/{SUCCESS_FILENAME}"):
        print(
            f"No-op. This notification was not for a {SUCCESS_FILENAME} file.")
        return

    prefix_to_load = removesuffix(object_id, SUCCESS_FILENAME)
    gsurl = f"gs://{bucket_id}/{prefix_to_load}"
    gcs_client = storage.Client(client_info=CLIENT_INFO)
    bkt = gcs_client.lookup_bucket(bucket_id)
    success_blob: storage.Blob = bkt.blob(object_id)
    success_blob.reload()
    success_created_unix_timestamp = success_blob.time_created.timestamp()

    # Need to handle potential duplicate Pub/Sub notifications.
    # To achieve this we will drop an empty "claimed" file that indicates
    # an invocation of this cloud function has picked up the success file
    # with a certain creation timestamp. This will support republishing the
    # success file as a mechanism of re-running the ingestion while avoiding
    # duplicate ingestion due to multiple Pub/Sub messages for a success file
    # with the same creation time.
    claim_blob: storage.Blob = bkt.blob(
        f"_claimed_{success_created_unix_timestamp}")
    try:
        claim_blob.upload_from_string(
            "",
            if_generation_match=0)
    except PreconditionFailed as err:
        raise RuntimeError(
            f"The prefix {gsurl} appears to already have been claimed for "
            f"{gsurl}{SUCCESS_FILENAME} with created timestamp"
            f"{success_created_unix_timestamp}."
            "This means that another invocation of this cloud function has"
            "claimed the ingestion of this batch."
            "This may be due to a rare duplicate delivery of the Pub/Sub "
            "storage notification.") from err

    destination_match = dest_re.match(object_id)
    if not destination_match:
        raise RuntimeError(f"Object ID {object_id} did not match regex:"
                           f" {destination_regex}")
    destination_details = destination_match.groupdict()
    try:
        dataset = destination_details['dataset']
        table = destination_details['table']
    except KeyError:
        raise RuntimeError(
            f"Object ID {object_id} did not match dataset and table in regex:"
            f" {destination_regex}") from KeyError
    partition = destination_details.get('partition')
    batch_id = destination_details.get('batch')
    labels = DEFAULT_JOB_LABELS
    labels["bucket"] = bucket_id

    if batch_id:
        labels["batch-id"] = batch_id

    if partition:
        dest_table_ref = bigquery.TableReference.from_string(
            f"{dataset}.{table}{partition}", default_project=project)
    else:
        dest_table_ref = bigquery.TableReference.from_string(
            f"{dataset}.{table}", default_project=project)

    default_query_config = bigquery.QueryJobConfig()
    default_query_config.use_legacy_sql = False
    default_query_config.labels = labels
    bq_client = bigquery.Client(client_info=CLIENT_INFO,
                                default_query_job_config=default_query_config)

    print(f"looking for {gsurl}_config/bq_transform.sql")
    external_query_sql = read_gcs_file_if_exists(
        gcs_client, f"{gsurl}_config/bq_transform.sql")
    print(f"external_query_sql = {external_query_sql}")
    if not external_query_sql:
        external_query_sql = look_for_transform_sql(gcs_client, gsurl)
    if external_query_sql:
        print("EXTERNAL QUERY")
        external_query(gcs_client, bq_client, gsurl, external_query_sql,
                       dest_table_ref)
        return

    print("LOAD_JOB")
    load_batches(gcs_client, bq_client, gsurl, dest_table_ref)


def external_query(gcs_client, bq_client, gsurl, query, dest_table_ref):
    """Load from query over external table from GCS.

    This hinges on a SQL query defined in GCS at _config/bq_transform.sql and
    an external table definition _config/external.json (otherwise will assume
    parquet external table)
    """
    external_table_config = read_gcs_file_if_exists(
        gcs_client, f"{gsurl}_config/external.json")
    if external_table_config:
        external_table_def = json.loads(external_table_config)
    else:
        print(f"Falling back to default parquet external table."
              f" {gsurl}/_config/external.json not found.")
        external_table_def = DEFAULT_EXTERNAL_TABLE_DEFINITION

    external_table_def["sourceUris"] = flatten(
        get_batches_for_prefix(gcs_client, gsurl))
    external_config = bigquery.ExternalConfig.from_api_repr(external_table_def)
    job_config = bigquery.QueryJobConfig(
        table_definitions={"temp_ext": external_config}, use_legacy_sql=False)
    # for some reason query string literal wrapped in b''
    rendered_query = str(
        str(query).format(dest_dataset=dest_table_ref.dataset_id,
                          dest_table=dest_table_ref.table_id))[2:-1]

    job: bigquery.QueryJob = bq_client.query(
        rendered_query,
        job_config=job_config,
        job_id_prefix=f"gcf-ingest-{dest_table_ref.dataset_id}-{dest_table_ref.table_id}-batch-1-of-1-",
    )

    print(f"started asynchronous query job: {job.job_id}")

    start_poll_for_errors = monotonic()
    # Check if job failed quickly
    while monotonic() - start_poll_for_errors < WAIT_FOR_JOB_SECONDS:
        job.reload()
        if job.errors:
            raise RuntimeError(
                f"query job {job.job_id} failed quickly: {job.errors}")
        sleep(1)


def flatten(arr: List[List[Any]]) -> List[Any]:
    """Flatten list of lists to flat list of elements"""
    return [j for i in arr for j in i]


def load_batches(gcs_client, bq_client, gsurl, dest_table_ref):
    """orchestrate 1 or more load jobs based on number of URIs and total byte
    size of objects at gsurl"""
    batches = get_batches_for_prefix(gcs_client, gsurl)
    load_config = construct_load_job_config(gcs_client, gsurl)
    load_config.labels = DEFAULT_JOB_LABELS
    batch_count = len(batches)

    for batch_num, batch in enumerate(batches):
        print(load_config.to_api_repr())
        job: bigquery.LoadJob = bq_client.load_table_from_uri(
            batch,
            dest_table_ref,
            job_config=load_config,
            job_id_prefix=f"gcf-ingest-{dest_table_ref.dataset_id}"
            f"-{dest_table_ref.table_id}"
            f"{batch_num}-of-{batch_count}-",
        )

        print(
            f"started asyncronous bigquery load job with id: {job.job_id} for"
            f" {gsurl}")

        start_poll_for_errors = monotonic()
        # Check if job failed quickly
        while monotonic() - start_poll_for_errors < WAIT_FOR_JOB_SECONDS:
            # Check if job failed quickly
            job.reload()
            if job.errors:
                raise RuntimeError(
                    f"load job {job.job_id} failed quickly: {job.errors}")
            sleep(1)


def _get_parent_config_file(storage_client, config_filename, bucket, path):
    config_dir_name = "_config"
    parent_path = Path(path).parent
    config_path = parent_path / config_dir_name / config_filename
    return read_gcs_file_if_exists(storage_client,
                                   f"gs://{bucket}/{config_path}")


def look_for_transform_sql(storage_client: storage.Client,
                           gsurl: str) -> Optional[str]:
    """look in parent directories for _config/bq_transform.sql"""
    config_filename = "bq_transform.sql"
    bucket_name, obj_path = _parse_gcs_url(gsurl)
    parts = removesuffix(obj_path, "/").split("/")

    def _get_parent_query(path):
        return _get_parent_config_file(storage_client, config_filename,
                                       bucket_name, path)

    config = None
    while parts:
        if config:
            return config
        config = _get_parent_query("/".join(parts))
        parts.pop()
    return config


def construct_load_job_config(storage_client: storage.Client,
                              gsurl: str) -> bigquery.LoadJobConfig:
    """
    merge dictionaries for loadjob.json configs in parent directories.
    The configs closest to gsurl should take precedence.
    """
    config_filename = "load.json"
    bucket_name, obj_path = _parse_gcs_url(gsurl)
    parts = removesuffix(obj_path, "/").split("/")

    def _get_parent_config(path):
        return _get_parent_config_file(storage_client, config_filename,
                                       bucket_name, path)

    config_q: Deque[Dict[str, Any]] = deque()
    config_q.append(BASE_LOAD_JOB_CONFIG)
    while parts:
        config = _get_parent_config("/".join(parts))
        if config:
            config_q.append(json.loads(config))
        parts.pop()

    merged_config = dict()
    while config_q:
        merged_config.update(config_q.popleft())
    print(f"merged_config: {merged_config}")
    return bigquery.LoadJobConfig.from_api_repr({"load": merged_config})


def get_batches_for_prefix(storage_client,
                           prefix_path,
                           ignore_subprefix="_config/",
                           ignore_file=SUCCESS_FILENAME) -> List[List[str]]:
    """
    This function creates batches of GCS uris for a given prefix.
    This prefix could be a table prefix or a partition prefix inside a
    table prefix.
    :param storage_client:
    :param prefix_path:
    :return: Array of their batches(one batch has an array of multiple GCS uris)
    """
    batches = []
    bucket_name, prefix_name = _parse_gcs_url(prefix_path)

    prefix_filter = f"{prefix_name}"
    bucket = storage_client.lookup_bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix_filter, delimiter="/"))

    cumulative_bytes = 0
    max_batch_size = int(getenv("MAX_BATCH_BYTES", DEFAULT_MAX_BATCH_BYTES))
    batch: List[str] = []
    for blob in blobs:
        # API returns root prefix also. Which should be ignored.
        # Similarly, the _SUCCESS file should be ignored.
        # Finally, anything in the _config/ prefix should be ignored.
        if (blob.name
                not in {f"{prefix_name}/", f"{prefix_name}/{ignore_file}"}
                or blob.name.startswith(f"{prefix_name}/{ignore_subprefix}")):
            if blob.size == 0:    # ignore empty files
                print(f"ignoring empty file: gs://{bucket}/{blob.name}")
                continue
            cumulative_bytes += blob.size

            # keep adding until we reach threshold
            if cumulative_bytes <= max_batch_size or len(
                    batch) > MAX_URIS_PER_LOAD:
                batch.append(f"gs://{bucket_name}/{blob.name}")
            else:
                batches.append(batch.copy())
                batch.clear()
                batch.append(f"gs://{bucket_name}/{blob.name}")
                cumulative_bytes = blob.size

    # pick up remaining files in the final batch
    if len(batch) > 0:
        batches.append(batch.copy())
        batch.clear()

    if len(batches) > 1:
        print(f"split into {len(batches)} load jobs.")
    elif len(batches) == 1:
        print("using single load job.")
    else:
        raise RuntimeError("No files to load!")
    return batches


def parse_notification(notification: dict) -> Tuple[str, str]:
    """valdiates notification payload
    Args:
        notification(dict): Pub/Sub Storage Notification
        https://cloud.google.com/storage/docs/pubsub-notifications
    Returns:
        tuple of bucketId and objectId attributes
    Raises:
        KeyError if the input notification does not contain the expected
        attributes.
    """
    try:
        attributes = notification["attributes"]
        return attributes["bucketId"], attributes["objectId"]
    except KeyError:
        raise RuntimeError(
            "Issue with payload, did not contain expected attributes"
            f"'bucketId' and 'objectId': {notification}") from KeyError


def read_gcs_file(gcs: storage.Client, gsurl: str) -> str:
    """
    Read a GCS object as a string

    Args:
        gcs:  GCS client
        gsurl: GCS URI for object to read in gs://bucket/path/to/object format
    Returns:
        str
    """
    bucket_id, object_id = _parse_gcs_url(gsurl)
    bucket = gcs.bucket(bucket_id)
    blob = bucket.blob(object_id)
    return blob.download_as_bytes()


def read_gcs_file_if_exists(gcs: storage.Client, gsurl: str) -> Optional[str]:
    """return string of gcs object contents or None if the object does not exist
    """
    try:
        return read_gcs_file(gcs, gsurl)
    except NotFound:
        return None


def dict_to_bq_schema(schema: List[Dict]) -> List[bigquery.SchemaField]:
    """Converts a list of dicts to list of bigquery.SchemaField for use with
    bigquery client library. Dicts must contain name and type keys.
    The dict may optionally contain a mode key."""
    default_mode = "NULLABLE"
    return [
        bigquery.SchemaField(
            x["name"],
            x["type"],
            mode=x.get("mode") if x.get("mode") else default_mode)
        for x in schema
    ]


def _parse_gcs_url(gsurl: str) -> Tuple[str, str]:
    """Given a Google Cloud Storage URL (gs://<bucket>/<blob>), returns a
    tuple containing the corresponding bucket and blob.
    """

    parsed_url = urlparse(gsurl)
    if not parsed_url.netloc:
        raise ValueError("Please provide a bucket name")
    if parsed_url.scheme.lower() != "gs":
        raise ValueError(f"Schema must be to 'gs://'"
                         f"Current schema: '{parsed_url.scheme}://'")

    bucket = parsed_url.netloc
    # Remove leading '/' but NOT trailing one
    blob = parsed_url.path.lstrip("/")
    return bucket, blob


# To be added to built in str in python 3.9
# https://www.python.org/dev/peps/pep-0616/
def removesuffix(in_str: str, suffix: str) -> str:
    """removes suffix from a string."""
    # suffix='' should not call self[:-0].
    if suffix and in_str.endswith(suffix):
        return in_str[:-len(suffix)]
    return in_str[:]
