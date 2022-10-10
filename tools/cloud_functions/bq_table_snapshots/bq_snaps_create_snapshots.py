import logging
from google.cloud import bigquery
from datetime import datetime
from dateutil.relativedelta import relativedelta
from google.api_core import client_info as http_client_info
import json 
import logging
import time
import base64

# id of project used for BQ storage
BQ_DATA_PROJECT_ID = "pso-dev-whaite"
# id of project used for BQ compute
BQ_JOBS_PROJECT_ID = "pso-dev-whaite"


def get_bq_client():
    client_info = http_client_info.ClientInfo(user_agent=f"google-pso-tool/bq-snapshots/0.0.1")
    client = bigquery.Client(project=BQ_JOBS_PROJECT_ID, client_info=client_info)
    return client


def create_snapshot(client, message):
    source_project_id = message['source_project_id']
    source_dataset_name = message['source_dataset_name']
    target_dataset_name = f"SNAPSHOT_{source_dataset_name}"
    seconds_before_expiration = message['seconds_before_expiration']
    snapshot_timestamp = message['snapshot_timestamp']

    current_date = datetime.now().strftime("%Y%m%d")
    snapshot_expiration_date = datetime.now() + relativedelta(seconds=int(seconds_before_expiration))

    source_table_name = message['source_table_name']
    snapshot_name = f"{BQ_DATA_PROJECT_ID}.{target_dataset_name}.{source_table_name}_{current_date}"
    source_table_fullname = f"{source_project_id}.{source_dataset_name}.{source_table_name}@{snapshot_timestamp}"

    job_config = bigquery.CopyJobConfig()
    job_config.operation_type = "SNAPSHOT"
    job_config._properties["copy"]["destinationExpirationTime"] = snapshot_expiration_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    job = client.copy_table(source_table_fullname, snapshot_name, job_config=job_config)
    logging.info(f"Creating snapshot for table: {snapshot_name}")
    return job


def hello_pubsub(event, context):
    """
    event should containa payload like:
    {
        'source_project_id': 'pso-dev-whaite', 
        'source_dataset_name': 'DATASET_1', 
        'source_table_name': 'test_table_1', 
        'snapshot_timestamp': 1665426373054, 
        'seconds_before_expiration': 2592000
    }
    """
    message = base64.b64decode(event['data']).decode('utf-8')
    message = json.loads(message)
    
    client = get_bq_client()
    job = create_snapshot(client, message)

    while True:
        if job.done():
            exception = job.exception()
            if exception:
                logging.info(str(exception))
                raise Exception(str(exception))
            else:
                return 'ok'
        time.sleep(2)