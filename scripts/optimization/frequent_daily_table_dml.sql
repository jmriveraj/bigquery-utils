/*
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * The following script will return tables that have had > 24 DML statements
 * run against in any one day within the past 30 days.
 * 30 days is the default timeframe, but you can change this by setting the
 * num_days_to_scan variable to a different value.
 */

DECLARE num_days_to_scan INT64 DEFAULT 30;

CREATE SCHEMA IF NOT EXISTS optimization_workshop;
CREATE OR REPLACE TABLE optimization_workshop.frequent_daily_table_dml
(
  dml_execution_date DATE,
  daily_dml_per_table INT64,
  table_id STRING,
  table_url STRING,
  job_ids ARRAY<STRING>,
  job_urls ARRAY<STRING>,
  statement_types ARRAY<STRING>,
  sum_total_gb_processed FLOAT64,
  avg_total_gb_processed FLOAT64,
  sum_total_slot_ms INT64,
  avg_total_slot_ms FLOAT64,
  sum_avg_slots FLOAT64,
  avg_avg_slots FLOAT64,
) AS

INSERT INTO optimization_workshop.frequent_daily_table_dml
SELECT
  EXTRACT(DATE FROM creation_time) AS dml_execution_date,
  COUNT(1) AS daily_dml_per_table,
  destination_table.project_id || '.' || destination_table.dataset_id || '.' || destination_table.table_id AS table_id,
  bqutil.fn.table_url(destination_table.project_id || '.' || destination_table.dataset_id || '.' || destination_table.table_id) AS table_url,
  ARRAY_AGG(job_id) AS job_ids,
  ARRAY_AGG(bqutil.fn.job_url(project_id || ':us.' || job_id) IGNORE NULLS) AS job_urls,
  ARRAY_AGG(DISTINCT statement_type) AS statement_types,
  SUM(SAFE_DIVIDE(total_bytes_processed, pow(2,30))) AS sum_total_gb_processed,
  AVG(SAFE_DIVIDE(total_bytes_processed, pow(2,30))) AS avg_total_gb_processed,
  SUM(total_slot_ms) AS sum_total_slot_ms,
  AVG(total_slot_ms) AS avg_total_slot_ms,
  SUM(SAFE_DIVIDE(total_slot_ms, (TIMESTAMP_DIFF(end_time, start_time, MILLISECOND)))) AS sum_avg_slots,
  AVG(SAFE_DIVIDE(total_slot_ms, (TIMESTAMP_DIFF(end_time, start_time, MILLISECOND)))) AS avg_avg_slots,
FROM
  `region-us`.INFORMATION_SCHEMA.JOBS_BY_ORGANIZATION
WHERE 1=1 -- no op filter to allow easy commenting below
-- Look at the past 30 days of jobs
AND creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL num_days_to_scan DAY)
-- Only look at DML statements
AND statement_type IN ('INSERT', 'UPDATE', 'DELETE', 'MERGE')
GROUP BY dml_execution_date, table_id, table_url
HAVING daily_dml_per_table > 24;
