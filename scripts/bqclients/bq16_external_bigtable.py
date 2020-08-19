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

""" 16) Added support for creating external BQ tables in the given bq dataset for allbigtable tables in the given bigtable instance id
    or for a given BT table

Note : Make sure the instances are in the regions and zones specified here : https://cloud.google.com/bigquery/external-data-sources
"""

from datetime import datetime
from datetime import timedelta
from google.cloud import bigquery
from google.oauth2 import service_account
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud import storage
from google.cloud import bigtable

# Used for asynchronous query executions
from google.cloud.bigquery.job import QueryJob

from google.cloud.bigquery.dataset import Dataset

import google.cloud.logging
import os
import os.path
import sys
import logging
import argparse
import ast
import json
import traceback
import uuid
import re

import concurrent.futures

__author__ = 'nikunjbhartia@google.com (Nikunj Bhartia)'

StartTime = datetime.now()

# Reference : https://docs.python.org/3/library/datetime.html#strftime-strptime-behavior
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

_PROJECT_ID = None

# This file has to be created based on the documentation :
# https://cloud.google.com/iam/docs/creating-managing-service-account-keys#iam-service-account-keys-create-console
_CRED_FILE = None

# Priority of query file > query text
_QUERY = None

# Setting this for dev phase. Ideally should be set as None
_QUERY_FILE = None
_QUERY_PARAMS = None
_DRY_RUN_FLAG = False
_QUERY_CACHE_FLAG = True
_QUERY_MODE = "sync"
_QUERY_RANGE_START = 1
_QUERY_RANGE_END = 10

_AUTH_VIEW_SOURCE_DATASET = ""
_AUTH_VIEW_SHARED_DATASET = ""
_AUTH_VIEW_SHARED_VIEW = ""

# Eg : gs://bucket_name/path/to/blob
_GCS_PATH = ''
# The following are derived from the above variable

# Derived : bucket_name
_GCS_BUCKET = ''

# Derived :  /path/to/blob/test-file.csv
_GCS_FILEBLOB_PATH = ''

# Eg : resources/flatfiles/test-file.csv
_UPLOAD_FILE = ''

# Derived from upload file and gcs paths above : gs://bucket_name/path/to/blob/test-file.csv
_GCS_FILE_URI = None

_BQTABLE_NAME = None

# Log target options
# file, stackdriver, stackdriverandfile, stdout
_LOG_TARGET = "stdout"
_LOGGER_NAME = "bqclient"
_LOG_LEVEL = logging.DEBUG

# Note : Default path and filename of the log file unless specified during calling the script
_LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
_LOG_FILE = _LOG_DIR + "/" + datetime.now().strftime("%Y%m%d") + "_" + "bqclient.log"

_BT_INSTANCE_ID = None
_BQ_DATASET_ID = None
_BT_TABLE_ID = None
_BT_SAMPLE_BATCH = 1

# cloud client credentials
_CREDENTIALS = None
_CLOUD_PLATFORM_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'

# POSIX standard exit codes
_EXIT_CODES = {
    "FileNotFound" : os.EX_NOINPUT, # An input file did not exist or was not readable.
    "PermissionDenied" : os.EX_NOPERM, # Insufficient permissions to perform the operation
    "Success" : os.EX_OK, #No error occurred
    "Failure" : os.EX_SOFTWARE # Internal software error
}

_LOG_LEVELS = {
    "debug" : logging.DEBUG,
    "warn" : logging.WARN,
    "error" : logging.ERROR,
    "info" : logging.INFO
}

_MAX_CONCURRENT_PROCESSES=10

Logger = None
BigqueryClient = None
GCSClient = None
BigtableClient = None

class CustomJsonFormatter(logging.Formatter):
    """Custom Log formatter for supporting structured logging.

    Args:
        message : Log text
        extraAgrs : [Optional] A dictionary of extra parameters to be clubbed with the final json log structure

    Returns:
        If log target is stackdriver : Json log structure (dict of k,v pairs) clubbed with input arguments and extra log record attributes
        Else : String representation of the dictionary (reason below)
    """
    def format(self, record):
        # We need this because If we simply log a struct, stackdriver would still take it as a string
        # Reference : https://googleapis.dev/python/logging/latest/handlers.html
        # Note : A logRecord instance is created automatically whenever a logger logs something
        # For more info about log record attributes : https://docs.python.org/3/library/logging.html#logrecord-attributes
        log_struct = {} if record.args == () else record.args
        log_struct['logText'] = record.msg
        log_struct['scriptFilename'] = record.filename
        log_struct['funcName'] = record.funcName
        log_struct['processId'] = record.process

        # Can be used as an identifier while debugging
        log_struct['threadId'] = record.thread

        # stackdriver captures the below information implicitly but we would need these for other log targets eg file / stdout
        if _LOG_TARGET != "stackdriver":
            log_struct['levelName'] = record.levelname
            log_struct['eventTimestamp'] = datetime.fromtimestamp(record.created).strftime(_DATE_FORMAT)


        # If log target is stackdriver and we return a json dump, then stackdriver treats this as string
        # If log target is file then not doing a json dump would give an error stream.write(dict + str) not allowed
        # Note : If log target is chosen as stackdriverandfile, in that case, this would return a json dump
        #        thereby forcing stackdriver to treat the dict as string
        return log_struct if _LOG_TARGET == 'stackdriver' else json.dumps(log_struct)


def set_global_vars(args):
    """Sets values of the global flags / parameters with the input paramaters or with default values"""
    global _PROJECT_ID, _DRY_RUN_FLAG, _CRED_FILE, _QUERY, _QUERY_FILE, _LOG_TARGET, _LOGGER_NAME, \
        _CREDENTIALS, _LOG_LEVEL, _LOG_FILE, _QUERY_CACHE_FLAG, _QUERY_PARAMS, _QUERY_MODE, _QUERY_RANGE_START, \
        _QUERY_RANGE_END, _MAX_CONCURRENT_PROCESSES, _UPLOAD_FILE, _BQTABLE_NAME, _GCS_PATH, _GCS_BUCKET, \
        _GCS_FILEBLOB_PATH, _GCS_FILE_URI, _AUTH_VIEW_SOURCE_DATASET, _AUTH_VIEW_SHARED_DATASET, _AUTH_VIEW_SHARED_VIEW, \
    _BT_INSTANCE_ID, _BT_TABLE_ID, _BQ_DATASET_ID, _BT_SAMPLE_BATCH

    _CRED_FILE = args.credfile if args.credfile is not None else _CRED_FILE

    # When your application needs access to user data, it asks Google for a particular scope of access.
    # Access tokens are associated with a scope, which limits the token's access
    # References: https://developers.google.com/drive/api/v2/about-auth
    #             https://cloud.google.com/bigquery/docs/authorization
    #             https://tools.ietf.org/html/rfc6749#section-3.3
    _CREDENTIALS = service_account.Credentials.from_service_account_file(
            _CRED_FILE,
            scopes=[_CLOUD_PLATFORM_SCOPE],
        )

    _PROJECT_ID = args.project_id if args.project_id  else  _CREDENTIALS.project_id
    _DRY_RUN_FLAG = (args.dry_run.lower() in ("yes", "true", "1")) if args.dry_run else _DRY_RUN_FLAG
    _QUERY_CACHE_FLAG = (args.query_cache.lower() in ("yes", "true", "1")) if args.query_cache else _QUERY_CACHE_FLAG
    _QUERY = args.query if args.query  else _QUERY
    _QUERY_FILE = args.queryfile if args.queryfile else _QUERY_FILE
    _QUERY_MODE = args.query_mode.lower() if args.query_mode else _QUERY_MODE
    _QUERY_RANGE_START = int(args.query_range_start) if  args.query_range_start else _QUERY_RANGE_START
    _QUERY_RANGE_END = int(args.query_range_end) if  args.query_range_end else _QUERY_RANGE_END
    _LOG_TARGET = args.logtarget if args.logtarget  else _LOG_TARGET
    _LOG_FILE = args.logfile if args.logfile  else _LOG_FILE
    _LOGGER_NAME = args.logger_name if args.logger_name else _LOGGER_NAME
    _QUERY_PARAMS = args.query_params if args.query_params else _QUERY_PARAMS
    _LOG_LEVEL = _LOG_LEVELS[args.loglevel.lower()] if args.loglevel else _LOG_LEVEL
    _MAX_CONCURRENT_PROCESSES = int(args.max_processes) if args.max_processes else _MAX_CONCURRENT_PROCESSES
    _BQTABLE_NAME = args.bqtable_name if args.bqtable_name else _BQTABLE_NAME
    # eg : 'resources/flatfiles/test-file.csv'
    _UPLOAD_FILE = args.upload_file if args.upload_file else _UPLOAD_FILE
    # Eg : _GCS_PATH : gs://bucket_name/path/to/blob
    _GCS_PATH = args.gcs_path if args.gcs_path else _GCS_PATH

    # Derived bucket name from _GCS_PATH : bucket_name
    bucket_match = re.findall(r"gs:\/\/(.*?)\/", _GCS_PATH)
    _GCS_BUCKET =  bucket_match[0] if bucket_match else _GCS_BUCKET

    # Derived from _GCS_PATH = /path/to/blob/
    blob_match = re.findall(r"gs:\/\/.*?\/(.*)$", _GCS_PATH)
    blob_base_path = blob_match[0] if blob_match else ''
    # Derived file blob path from blob_base_path and _UPLOAD_FILE : /path/to/blob/test-file.csv
    _GCS_FILEBLOB_PATH = blob_base_path + os.path.basename(_UPLOAD_FILE) if _GCS_PATH else _GCS_FILEBLOB_PATH

    # Derived : gs://bucket_name/path/to/blob/test-file.csv
    _GCS_FILE_URI = "gs://" + _GCS_BUCKET + "/" + _GCS_FILEBLOB_PATH

    _AUTH_VIEW_SOURCE_DATASET = args.authview_source_datasetid if args.authview_source_datasetid else _AUTH_VIEW_SOURCE_DATASET
    _AUTH_VIEW_SHARED_DATASET = args.authview_shared_datasetid if args.authview_shared_datasetid else _AUTH_VIEW_SHARED_DATASET
    _AUTH_VIEW_SHARED_VIEW = args.authview_shared_viewid if args.authview_shared_viewid else _AUTH_VIEW_SHARED_VIEW

    _BT_INSTANCE_ID = args.bt_instance_id if args.bt_instance_id else _BT_INSTANCE_ID
    _BT_TABLE_ID = args.bt_table_id if args.bt_table_id else _BT_TABLE_ID
    _BQ_DATASET_ID = args.bq_dataset_id if args.bq_dataset_id else _BQ_DATASET_ID
    _BT_SAMPLE_BATCH = int(args.bt_sample_batch) if args.bt_sample_batch else _BT_SAMPLE_BATCH

def log_params():
    """Logs all the script global flags and parameters. Valid only in case debug mode is on. """
    globalparams = {
        "credFilepath" : _CRED_FILE,
        "projectId" : _PROJECT_ID,
        "dryRun" : _DRY_RUN_FLAG,
        "queryCacheFlag" : _QUERY_CACHE_FLAG,
        "queryParams" : _QUERY_PARAMS,
        "queryMode" : _QUERY_MODE,
        "queryRangeStart" : _QUERY_RANGE_START,
        "queryRangeEnd" : _QUERY_RANGE_END,
        "maxProcesses" : _MAX_CONCURRENT_PROCESSES,
        "query" : _QUERY,
        "queryFile" : _QUERY_FILE,
        "logTarget" : _LOG_TARGET,
        "logFile" : _LOG_FILE,
        "loggerName" : _LOGGER_NAME,
        "logLevel" : logging.getLevelName(_LOG_LEVEL),
        "serviceAccount" : _CREDENTIALS.service_account_email,
        "uploadFile" : _UPLOAD_FILE,
        "gcsPath" : _GCS_PATH,
        "gcsBucket" : _GCS_BUCKET,
        "gcsFileBlobPath" : _GCS_FILEBLOB_PATH,
        "gcsFileUri" : _GCS_FILE_URI,
        "bqtableName" : _BQTABLE_NAME,
        "authViewSourceDatasetId" : _AUTH_VIEW_SOURCE_DATASET,
        "authViewSharedDatasetId" : _AUTH_VIEW_SHARED_DATASET,
        "authViewSharedViewId" : _AUTH_VIEW_SHARED_VIEW,
        "bigtableInstanceId" : _BT_INSTANCE_ID,
        "bigtableTableId" : _BT_TABLE_ID,
        "bigqueryDatasetId" : _BQ_DATASET_ID,
        "bigtableSampleBatch" :_BT_SAMPLE_BATCH
     }

    Logger.debug("Script Properties", globalparams)


def create_directories(filename):
    """Creates directory paths for input log file in case given path doesn't exist"""
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename), exist_ok=True)


def init_logger():
    """Initializes global Logger with appropriate handlers and formatters"""
    global Logger, _LOG_TARGET
    Logger = logging.getLogger(_LOGGER_NAME)

    # Log target options
    # file, stackdriver, stackdriverandfile, stdout
    if _LOG_TARGET == "stackdriver":
        # Stackdriver as log target
        cloudlog_client = google.cloud.logging.Client(credentials=_CREDENTIALS, project=_PROJECT_ID)
        cloudlog_handler = CloudLoggingHandler(cloudlog_client)
        cloudlog_handler.setFormatter(CustomJsonFormatter())
        Logger.addHandler(cloudlog_handler)

    elif _LOG_TARGET == "stackdriverandfile":
        # File and Stackdriver as log targets
        # Note:  One can add any number of different handlers to the logger
        create_directories(_LOG_FILE)
        cloudlog_client = google.cloud.logging.Client(credentials=_CREDENTIALS, project=_PROJECT_ID)
        cloudlog_handler = CloudLoggingHandler(cloudlog_client)
        cloudlog_handler.setFormatter(CustomJsonFormatter())

        filelog_handler = logging.handlers.RotatingFileHandler(_LOG_FILE, maxBytes=1024*100, backupCount=5)
        filelog_handler.setFormatter(CustomJsonFormatter())

        # Add log handlers for both stakdriver and file to logger
        Logger.addHandler(cloudlog_handler)
        Logger.addHandler(filelog_handler)

    elif _LOG_TARGET == "file":
        # File as log target
        # Setting config for rotating log files
        # One can modify the config from size based log rotation to time based log rotation using TimeRotatingFieldHandler class
        # Refernce : https://docs.python.org/2.6/library/logging.html
        create_directories(_LOG_FILE)
        filelog_handler = logging.handlers.RotatingFileHandler(_LOG_FILE, maxBytes=1024*100, backupCount=5)
        filelog_handler.setFormatter(CustomJsonFormatter())
        Logger.addHandler(filelog_handler)

    else:
        # Defaults to stdout log target
        # Sets log target global var if input logtarget param is out of scope
        _LOG_TARGET = "stdout"
        stdoutlog_handler = logging.StreamHandler(sys.stdout)
        stdoutlog_handler.setFormatter(CustomJsonFormatter())
        Logger.addHandler(stdoutlog_handler)

    # If we set the below config somehow prints the first string of every log line!
    # logging.basicConfig(filename=_LOG_FILE, format='%(message)s')

    Logger.setLevel(_LOG_LEVEL)


def init_bigquery_client():
    """Initializes bigquery client along with query flags and query paramaters"""
    global BigqueryClient

    # Reference for job parameters : https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.job.QueryJobConfig.html
    bq_jobconfig = bigquery.QueryJobConfig()

    # Support for parameterized queries
    # Reference :https://cloud.google.com/bigquery/docs/parameterized-queries
    # Eg: _QUERY_PARAMS = "[('tags','STRING','%google-bigquery%'), ('limit','INT64',10)]"
    #                or = "[(None,'STRING','%google-bigquery%'), (None,'INT64',10)]"
    if _QUERY_PARAMS:
        params = []
        # ast.literal_eval(x) is used to convert string representation of a list to list object
        for elem in ast.literal_eval(_QUERY_PARAMS):
            # consider input parameter only if all the three key values : ("variable-name", "variable-datatype", "variable-value") are given
            if len(elem) == 3:
                params.append(bigquery.ScalarQueryParameter(elem[0], elem[1], elem[2]))
            else:
                Logger.info("Skipping an input parameter. One of the three values ('var1-name' or None, 'var1-datatype', 'var1-value') missing in : %s"%(str(elem)))

        bq_jobconfig.query_parameters = params

    bq_jobconfig.dry_run = _DRY_RUN_FLAG
    bq_jobconfig.use_query_cache = _QUERY_CACHE_FLAG

    BigqueryClient = bigquery.Client(credentials=_CREDENTIALS, project=_PROJECT_ID, default_query_job_config=bq_jobconfig)


def init_gcs_client():
    """Initializes gcs storage"""
    global GCSClient

    # Api Reference : https://googleapis.dev/python/storage/latest/client.html
    GCSClient = storage.Client(credentials=_CREDENTIALS, project=_PROJECT_ID )

# Ref : https://googleapis.dev/python/bigtable/latest/client.html
def init_bigtable_client():
    """Initializes bigtable client"""
    global BigtableClient
    BigtableClient = bigtable.Client(admin=True, credentials=_CREDENTIALS, project=_PROJECT_ID)


def gcs_bucket_details(gcsbucket):
    return {
          "gcsBucket" : gcsbucket.name,
          "selfLink" : gcsbucket._properties.get("selfLink"),
          "gcsBucketTimeCreated" : gcsbucket._properties.get("timeCreated"),
          "gcsBucketTimeUpdated" : gcsbucket._properties.get("updated"),
          "gcsIamConfig": gcsbucket._properties.get("iamConfiguration"),
          "gcsLocati_CREDEon": gcsbucket._properties.get("location"),
          "gcsLocationType": gcsbucket._properties.get("locationType"),
          "gcsStorageClass" : gcsbucket._properties.get("storageClass")
    }


def create_gcs_bucket():
    """API call: create a new bucket via a POST request."""
    #  Refernces :
    #  https://googleapis.dev/python/storage/latest/client.html
    #  https://cloud.google.com/storage/docs/json_api/v1/buckets/insert
    gcsbucket = ""

    try:
        gcsbucket = GCSClient.create_bucket(_GCS_BUCKET)

        Logger.info("Gcs bucket created", gcs_bucket_details(gcsbucket))
        
    except google.cloud.exceptions.Conflict:
        Logger.info("Given bucket : {} already exists. ".format(_GCS_BUCKET))
    
    except Exception as error:
        Logger.error("Exception during creating gcs bucket", { 'exceptionInfo' : traceback.format_exc() })
        raise


def upload_file_to_gcs():
    """Uploads a file to the bucket."""
    try:
        gcsbucket = GCSClient.get_bucket(_GCS_BUCKET)

        Logger.debug("Trying to upload file to GCS bucket", gcs_bucket_details(gcsbucket))

        blob = gcsbucket.blob(_GCS_FILEBLOB_PATH)
        blob.upload_from_filename(_UPLOAD_FILE)

    except Exception as error:
        Logger.error("Exception during uploading file to gcs bucket", { 'exceptionInfo' : traceback.format_exc() })
        raise

    Logger.info('File uploaded to gcs bucket', { "sourceFileName" : _UPLOAD_FILE, "gcsFilePath" : _GCS_FILE_URI})


def load_gcsfile_to_bq():
    """Loads uploaded csv file from gcs to given Bigquery tablename and creates table autodetecing schema from input file if not present"""

    # Setting default exit code
    exit_code = _EXIT_CODES["Success"]

    # Reference  :https://cloud.google.com/bigquery/docs/loading-data-cloud-storage-csv
    job_config = bigquery.LoadJobConfig()
    job_config.skip_leading_rows = 1
    job_config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE

    # Auto detect schema from the csv file
    # reference  :https://cloud.google.com/bigquery/docs/schema-detect
    job_config.autodetect = True

    try:
        # API request
        # Reference  :https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.client.Client.html?highlight=load_table_from_uri#google.cloud.bigquery.client.Client.load_table_from_uri
        load_job = BigqueryClient.load_table_from_uri(_GCS_FILE_URI, _BQTABLE_NAME, job_config=job_config)

        Logger.info("Starting bq load job {}".format(load_job.job_id))

        # Blocking call - Waits for table load to complete.
        load_job.result()

        log_bqloadjob_stats(load_job)
        
        Logger.info("BQ load Job finished.")
        
    except KeyError as error:
        Logger.error("Failure in fetching bq load job stats ", { 'exceptionInfo' : traceback.format_exc() })
        raise
    except AttributeError as error:
        Logger.error("Failure in fetching bq load job stats ", { 'exceptionInfo' : traceback.format_exc() })
        raise
    except Exception as error:
        Logger.error("Exception during bq load job execution ", { 'exceptionInfo' : traceback.format_exc() })
        raise

    return exit_code



def init_query_text():
    """Sets global query text. Priority of input queryfile > input query string (if both are set during script call)"""
    global _QUERY
    try:
        # If query file is not passed as input argument, then it takes the input query text (set during the initializing global params )
        if _QUERY_FILE:
            with open(_QUERY_FILE, 'r') as file:
                _QUERY = file.read()
    except Exception as error:
        Logger.error("Exception during query fetch", { 'exceptionInfo' : traceback.format_exc() })
        raise

    Logger.info("Query fetch successful", { 'query' : _QUERY })


def run_bulk_asyn_queries(start_id, end_id):
    """Initializes a pool of processes to execute calls asynchronously.
        Reference : https://docs.python.org/3/library/concurrent.futures.html#processpoolexecutor

    Args :
         start_id: Starting Id for the query
         end_id: Ending Id for the query
    """

    with concurrent.futures.ProcessPoolExecutor(max_workers=_MAX_CONCURRENT_PROCESSES) as executor:
        list_query_params = []
        for id in range(start_id, end_id+1):
            status = "Initiated"
            creation_ts = (datetime.now() - timedelta(days=id))

            # Important Note : Change this as per your query
            # The below test case is for query : resource/insert_dml.sql
            list_query_params.append("[('id','INT64', {}), ('status','STRING', '{}'), ('creation_ts','STRING', '{}')]".format(id, status, creation_ts))

            # Sample query param for resource/update_dml.sql
            # list_query_params.append("[('id','INT64', {})]".format(id))

        for query_id in executor.map(run_async_query,list_query_params):
            Logger.info("Successfully executed query Id: {}".format(query_id))


def run_async_query(query_params):
    """Executes the dml with input query param dict and returns the queryId for reference
        ARgs :
            query_params in the form of "[('id','INT64', {}), ('status','STRING', '{}'), ('creation_ts','STRING', '{}')]"

        Return :
            queryID
    """
    Logger.info("Executing Query with params: " + query_params)

    bq_jobconfig = BigqueryClient._default_query_job_config
    params = []
    query_id = None
    for elem in ast.literal_eval(query_params):
        # consider input parameter only if all the three key values : ("variable-name", "variable-datatype", "variable-value") are given
        if len(elem) == 3:
            if elem[0] == 'id':
                query_id = elem[2]
            params.append(bigquery.ScalarQueryParameter(elem[0], elem[1], elem[2]))
        else:
            Logger.info("Skipping an input parameter. One of the three values ('var1-name' or None, 'var1-datatype', 'var1-value') missing in : %s"%(str(elem)))

    bq_jobconfig.query_parameters = params

    query_job = BigqueryClient.query(_QUERY, job_config=bq_jobconfig)
    process_query_results(query_job)
    return query_id


def run_query():
    """Runs a BigQuery SQL query and returns query results if the query completes within a specified timeout.
    Also logs stats (in case debug mode is on)

    Returns:
        0 in case of success, nonzero on failure.

    Raises:
        AttributeError, KeyError : In case the stats field are not resolvable due to some issue
        Exception : Failure during query runtime execution
    """

    # Setting default exit code
    exit_code = _EXIT_CODES["Success"]

    try :
        Logger.debug("Executing query job")

        # For synchronous call
        query_job = BigqueryClient.query(_QUERY)  #API request

        """For async call, use QueryJob class with callback. 
        Reference  :https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.job.QueryJob.html#google.cloud.bigquery.job.QueryJob.add_done_callback 
        Note : We need have to have some kind of a blocking mechanism until callback is called, otherwise the script will end before executing the callback"""
        # query_job = QueryJob(get_random_jobid(), _QUERY, BigqueryClient)
        # query_job.add_done_callback(process_query_results)

        #Blocking call to wait until query completes execution
        # query_job.result()

        # dry run mode doesn't have a result
        if not _DRY_RUN_FLAG:
            # The below function implements a blocking call until query completion or timeout
           process_query_results(query_job)

        log_query_stats(query_job)

    except KeyError as error:
        Logger.error("Failure in fetching query stats ", { 'exceptionInfo' : traceback.format_exc() })
        raise
    except AttributeError as error:
        Logger.error("Failure in fetching query stats ", { 'exceptionInfo' : traceback.format_exc() })
        raise
    except Exception as error:
        Logger.error("Exception during query execution ", { 'exceptionInfo' : traceback.format_exc() })
        raise

    return exit_code


def get_random_jobid():
    """Returns a random uuid, used in case of firing an asynchronous bigquery job"""
    return str(uuid.uuid1())


def log_bqloadjob_stats(load_job):
    """Logs load job stats. Valid when debug mode is on"""
    properties = load_job._properties

    loadjob_stats = {
        'state' : load_job.state,
        'jobId' : load_job.job_id,
        'inputFiles' : load_job.input_files,
        'inputFileBytes' : load_job.input_file_bytes,
        'outputRows' : load_job.output_rows,
        'outputBytes' : load_job.output_bytes,
        'totalSlotsMs' : properties['statistics']['totalSlotMs']
    }

    loadJobStartTime =  datetime.fromtimestamp(properties['statistics']['startTime']/1000)
    loadJobEndTime = datetime.fromtimestamp(properties['statistics']['endTime']/1000)

    loadjob_stats['loadJobStartTime'] = loadJobStartTime.strftime(_DATE_FORMAT)
    loadjob_stats['loadJobEndTime'] = loadJobEndTime.strftime(_DATE_FORMAT)
    loadjob_stats['loadJobRuntimeSecs'] = (loadJobEndTime - loadJobStartTime).total_seconds()

    Logger.debug("Bq load job Statistics", { 'queryStats' :  loadjob_stats })


def log_query_stats(query_job):
    """Logs query stats. Valid when debug mode is on"""
    query_stats = { 'state' : query_job.state,
                    'bytesProcessed' : query_job.total_bytes_processed,
                    'cacheHit' : query_job.cache_hit,
                    'jobId' : query_job.job_id }

    # Calculating Extra query stats in case dry run flag is not set as true
    if not _DRY_RUN_FLAG:
        queryStartTime =  datetime.fromtimestamp(query_job._properties['statistics']['startTime']/1000)
        queryEndTime = datetime.fromtimestamp(query_job._properties['statistics']['endTime']/1000)

        query_stats['queryStartTime'] = queryStartTime.strftime(_DATE_FORMAT)
        query_stats['queryEndTime'] = queryEndTime.strftime(_DATE_FORMAT)
        query_stats['queryRuntimeSecs'] = (queryEndTime - queryStartTime).total_seconds()

    Logger.debug("Query Statistics", { 'queryStats' :  query_stats })


def process_query_results(query_job):
    """ Modify to process the results as per requirement. Below example dumps every row into the chosen log target"""

    # This is Blocking Call and bails out until timeout is exceeded or query returns successfully
    results = query_job.result()
    for row in results:
        # row._class_ = google.cloud.bigquery.table.Row
        # Eg: row => Row(('https://stackoverflow.com/questions/22879669', 48540), {'url': 0, 'view_count': 1})
        #     list(row.items()) =>  [('url', 'https://stackoverflow.com/questions/22879669'),('view_count', 48540)]
        rowdict = dict(list(row.items()))
        Logger.info("Query result for every row", { 'result' : rowdict, 'jobId' : query_job.job_id })

    return _EXIT_CODES["Success"]


def get_all_dataset_views(dataset_id):
    """
        Scans through all the tables in a given dataset and identifies all the views.
        Note : Lists a max of 1000000 tables in a given dataset. Increase the value of max_results if required

        Args :
            dataset_id : fully-qualified ID in standard SQL format : <project_name>.<dataset_name>

        Returns :
            List of views in the given dataset.
                view.__class__ = google.cloud.bigquery.table.TableListItem

    """
    views = []
    count = 0

    # Api reference :https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.client.Client.html#google.cloud.bigquery.client.Client.list_tables
    tables = BigqueryClient.list_tables(dataset_id, max_results = 1000000)

    for table in tables:
        if table._properties.get("type") == 'VIEW':
            views.append(table)
            count = count+1
            Logger.debug("List View append count {count} : {view_name}".format(count=count, view_name=table.table_id))

    Logger.debug("View Stats", {"viewCount" : count, "tableCount": tables.num_results, "datasetId" : dataset_id})

    return views


def authorize_dataset_views(source_dataset_id, shared_dataset_id, shared_view_id):
    """
        Args :
            source_dataset_id :  dataset id containing the souce table
            shared_dataset_id :  dataset id containing the view(s) which needs access to the source data
            shared_view_id    :  view id which needs access to the source data

       Note :
            a) The ids need to be fully-qualified ID in standard SQL format :
               dataset : <project_name>.<dataset_name>
               view    : <project_name>.<dataset_name>.<table_name>
            b) Either one of the two args : shared_dataset_id or shared_view_id is manditory
            c) - If shared_dataset_id is given, the script scans through all the tables in the given dataset and authorizes all the views to access the source dataset
               - If shared_view_id is given, the script just authorized the given view to access the source dataset
            d) Handles duplicate access entries i.e pre authorized views in a given dataset are ignored
            e) Lists a max of 1000000 tables in a given dataset. Increase the value of max_results in the function get_all_dataset_views if required

    """
    exit_code = _EXIT_CODES["Success"]
    try:
        # Dataset object containing the source table
        # Api reference  :https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.client.Client.html#google.cloud.bigquery.client.Client.get_dataset
        source_dataset = BigqueryClient.get_dataset(source_dataset_id)

        # Access controls for the source dataset which needs to be shared with the dataset containing the views
        access_entries = source_dataset.access_entries

        #List of view in the dataset which need to be authorized for accessing the source table
        if shared_view_id:
            views = [BigqueryClient.get_table(shared_view_id)]
        else :
            views = get_all_dataset_views(shared_dataset_id)

        authorizated_views = []
        for view in views:
            # Update Access control List for every view in the source dataset
            # Note : Handling duplicate accessEntries
            #       The updated access entries may contain duplicate AccessEntries depending one/all whether on of the views were already authorized before
            #          thereby leasing to an error

            view_access_entry = bigquery.AccessEntry(None, 'view', view.reference.to_api_repr())

            if  view_access_entry not in access_entries :
                authorizated_views.append(view.table_id)
                access_entries.append(view_access_entry)
            else :
                Logger.info("View {} already authorized".format(view.table_id))

        # Updating access control for the source dataset
        source_dataset.access_entries = access_entries

        # Api reference : https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.client.Client.html#google.cloud.bigquery.client.Client.update_dataset
        source_dataset = BigqueryClient.update_dataset(source_dataset, ['access_entries'])  # API request

        Logger.info("Authorization Complete", {"viewAuthorizationCount" : len(authorizated_views), "viewsAuthorized" : authorizated_views, "sourceDatasetId" : source_dataset_id, "sharedDatasetId" : shared_dataset_id})

    except Exception as error:
        Logger.error("Exception during authorizing views", { 'exceptionInfo' : traceback.format_exc() })
        raise

    return exit_code


# Ref :
# https://cloud.google.com/bigquery/external-table-definition#tabledef-bigtable
# https://cloud.google.com/bigquery/docs/reference/rest/v2/tables#bigtableoptions
# Example :
# https://cloud.google.com/bigquery/external-data-bigtable#example
def create_bigtable_definition_config(bigtable_object):
    table_name = bigtable_object.table_id

    external_config_json = {
        "sourceFormat" : "BIGTABLE",
        "sourceUris": [ "https://googleapis.com/bigtable/projects/" + _PROJECT_ID + "/instances/" + _BT_INSTANCE_ID + "/tables/" + table_name ],
        "bigtableOptions": {
            "readRowkeyAsString" : "true",
            "columnFamilies" : []
        }
    }

    # Sampling only one column to get the schema. Can be further modified to read for sample records to get a more probable schema
    partial_rows = bigtable_object.read_rows(limit=_BT_SAMPLE_BATCH)

    table_schema = []
    # dict_keys([b'csv:a', b'csv:b']) where csv is the column family and a,b are the column names in the column family
    # list(dict_keys([b'csv:a', b'csv:b'])) = [b'csv:a', b'csv:b']
    # The list(Set().union .. = merges these column names for every row in the batch to get a unified table schema
    for row in partial_rows:
        table_schema = list(set().union(table_schema, list(row.to_dict().keys())))


    if table_schema:
        Logger.info("Creating ext BQ table pointint to BT", { "bqTableName" : table_name , "bqTableSchema": str(table_schema) })
        # Note: This map will have key as the column family and values contain a json having all the column names in that
        # family along with the type. Later on, we just need a list of the values in this map.
        # # This is made so that while iterating though all the column_family:column_name mappings, we can keep adding the columns in the
        # correspongind column_family key
        column_family_config_map = {}

        for family_columnname in table_schema:
            # Eg: b'csv:a'.decode('utf-8') --> 'csv:a'
            column_family, column_name = family_columnname.decode('utf-8').split(":")
            if column_family_config_map.get(column_family):
                column_family_config_map[column_family]["columns"].append({
                    "qualifierString": column_name,
                    "type": "STRING"
                })

            else :
                column_family_config_map[column_family] = {
                    "familyId": column_family,
                    "onlyReadLatest": "true",
                    "columns": [
                        {
                            "qualifierString": column_name,
                            "type": "STRING"
                        }
                    ]
                }

        external_config_json["bigtableOptions"]["columnFamilies"] = list(column_family_config_map.values())
        Logger.debug("Definition file for table : '{name}' created successfully".format(name = table_name))

        return external_config_json

    # If there is no data in the table, skip external table creation
    else:
        Logger.info("Skipping external BQ table creation. No data present in BT table : {name}".format(name=table_name))
        return _EXIT_CODES["Failure"]


# Ref : https://cloud.google.com/bigquery/external-data-bigtable
# https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.job.QueryJobConfig.html#google.cloud.bigquery.job.QueryJobConfig.table_definitions
# https://googleapis.dev/python/bigquery/latest/reference.html#external-configuration
def create_ext_bq_tables_for_bt():
    success_counter = 0
    try:
        bigtable_instance = BigtableClient.instance(_BT_INSTANCE_ID)

        if _BT_TABLE_ID:
            bt_tables = [bigtable_instance.table(_BT_TABLE_ID)]
        else:
            bt_tables = bigtable_instance.list_tables()

        for table in bt_tables:
            try:
                external_jsonconfig = create_bigtable_definition_config(table)
                if (external_jsonconfig != _EXIT_CODES["Failure"]):

                    ext_bq_table = bigquery.Table(_PROJECT_ID + "." + _BQ_DATASET_ID + "." + table.table_id)

                    # ref : https://googleapis.dev/python/bigquery/1.23.1/generated/google.cloud.bigquery.external_config.ExternalConfig.html#google.cloud.bigquery.external_config.ExternalConfig.from_api_repr
                    external_config = bigquery.ExternalConfig(bigquery.external_config.ExternalSourceFormat.BIGTABLE).from_api_repr(external_jsonconfig)
                    ext_bq_table.external_data_configuration = external_config

                    # Ref : https://googleapis.dev/python/bigquery/latest/generated/google.cloud.bigquery.client.Client.html#google.cloud.bigquery.client.Client.create_table
                    create_table = BigqueryClient.create_table(ext_bq_table, exists_ok = True)
                    success_counter = success_counter+1
                    Logger.debug("Successfully created external BQ table : {name}".format(name=table.table_id))

            except Exception as error:
                Logger.error("Exception during creation of external BQ table : {name}".format(name=table.table_id), { 'exceptionInfo' : traceback.format_exc() })


        Logger.debug("External BQ table creation job completed", {"totalBTtableCount" : len(bt_tables), "totalBQTablesCreated" : success_counter})
        return _EXIT_CODES["Success"]


    except Exception as error:
        Logger.error("Exception during creation of external BQ tables", { 'exceptionInfo' : traceback.format_exc() })
        return _EXIT_CODES["Failure"]


if __name__ == '__main__':
    """
    Args:
      List of arguments as strings.

    Returns:
      0 on success, nonzero on failure."""

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--project-id', help='Google Cloud project ID')
    parser.add_argument('--dry-run', help='Dry Run Flag for bigquery : true/false')
    parser.add_argument('--query-cache', help='Look for the query result in the cache : true/false')
    parser.add_argument('--query-mode', help='Run bulk queries : async / sync')
    parser.add_argument('--max-processes', help='Maximum number of parallel processes to run the bulk query load in async mode')
    parser.add_argument('--query-range-start', help='Run bulk queries asynchronously for a range id starting from this number')
    parser.add_argument('--query-range-end', help='Run bulk queries asynchronously for a range id ending from this number')
    parser.add_argument('--query-params', help='list of parameters for parameterized query. Eg "[("var1-name" or None, "var1-datatype", "var1-value"), ...]"')
    parser.add_argument('--credfile', help='Filepath of the service account credential file')
    parser.add_argument('--query', help='Input query')
    parser.add_argument('--queryfile', help='Filepath of the input query')
    parser.add_argument('--logtarget', help='Options : file, stackdriver, stackdriverandfile, stdout  #Defaults to stdout')
    parser.add_argument('--logger-name', help='Module Tag for every log record')
    parser.add_argument('--logfile', help="Output file path of logger if logger type 'file' is chosen")
    parser.add_argument('--loglevel', help="Define the required log level : debug, warn, error, info")
    parser.add_argument('--gcs-path', help="GCS file path to upload the file to. If the bucket is not present, it will create one")
    parser.add_argument('--upload-file', help="File path to upload in the given gcs-bucket")
    parser.add_argument('--bqtable-name', help="Fully qualified bigquery table name to load the data in the upload-file")
    parser.add_argument('--authview-source-datasetid', help="Fully qualified id for bigquery dataset containing the source tables")
    parser.add_argument('--authview-shared-datasetid', help="Fully qualified id for bigquery dataset containing the views those need to be authorized to access the given source table dataset")
    parser.add_argument('--authview-shared-viewid', help="Fully qualified id for bigquery view that needs to be authorized to access the given source table dataset"),
    parser.add_argument('--bt-instance-id', help="Source BT instance id"),
    parser.add_argument('--bt-table-id', help="Source BT table id (mention this to avoid creating external BQ tables for all BT tables in the given instance id)"),
    parser.add_argument('--bt-sample-batch', help="Number of rows to be sampled for schema derivation from a BT table"),
    parser.add_argument('--bq-dataset-id', help="Target BQ datasetid in the same project for creating the external BQ tables pointing to BT")

    args = parser.parse_args()

    set_global_vars(args)
    init_logger()
    init_bigquery_client()
    init_query_text()
    log_params()

    exit_code = _EXIT_CODES["Success"]

    if _GCS_PATH and _UPLOAD_FILE:
        init_gcs_client()
        create_gcs_bucket()
        exit_code = upload_file_to_gcs()

        if _BQTABLE_NAME:
            exit_code = load_gcsfile_to_bq()

    elif ( _QUERY or _QUERY_FILE ):
        if _QUERY_MODE == 'async':
            exit_code = run_bulk_asyn_queries(_QUERY_RANGE_START, _QUERY_RANGE_END)
        else:
            exit_code = run_query()

    elif (_AUTH_VIEW_SOURCE_DATASET and (_AUTH_VIEW_SHARED_DATASET or _AUTH_VIEW_SHARED_VIEW)) :
        # Passing the global variables here in an attempt to decrease the dependency on global variables so that these can later be encapsulated into a class
        exit_code = authorize_dataset_views(_AUTH_VIEW_SOURCE_DATASET, _AUTH_VIEW_SHARED_DATASET, _AUTH_VIEW_SHARED_VIEW)

    elif (_BT_INSTANCE_ID):
        init_bigtable_client()
        exit_code = create_ext_bq_tables_for_bt()


    EndTime = datetime.now()

    Logger.debug("Script statistics", { 'scriptStartTime' : StartTime.strftime(_DATE_FORMAT),
                                         'scriptEndTime' : EndTime.strftime(_DATE_FORMAT),
                                         'scriptRuntimeSecs' : (EndTime - StartTime).total_seconds() })

    sys.exit(exit_code)

