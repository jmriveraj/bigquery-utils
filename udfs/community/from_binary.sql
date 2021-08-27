/*
 * Copyright 2020 Google LLC
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

-- from_binary:
-- Input: STRING representing a number in binary form
-- Output: INT64 number in decimal form
CREATE OR REPLACE FUNCTION fn.from_binary(value STRING) AS 
(
  (
    SELECT 
      SUM(CAST(char AS INT64) << (LENGTH(value) - 1 - bit))
    FROM 
      UNNEST(SPLIT(value, '')) AS char WITH OFFSET bit
  )
);
