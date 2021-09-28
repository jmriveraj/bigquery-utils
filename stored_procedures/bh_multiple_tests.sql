-- Adjust p values using the Benjamini-Hochberg multipletests method, additional details in doi:10.1098/rsta.2009.0127
-- the implementation can be compared with the python function 'statsmodels.stats.multitest.multipletests' (method='fdr_bh')

-- @param STRING pvalue_table_name : the name of the table with the p values that need to be adjusted
-- @param STRING pvalue_column_name : the name of the column with p values.
-- @param INT Nrows : Number of tests (equal to number of rows of the input table)
CREATE OR REPLACE PROCEDURE bqutil.procedure.bh_multiple_tests (pvalue_table_name STRING, pvalue_column_name STRING, n_rows INT64)
BEGIN
   EXECUTE IMMEDIATE format("""
   CREATE TEMP TABLE bh_multiple_tests_results AS
   WITH padjusted_data AS (
       WITH ranked_data AS (
           SELECT *, ( DENSE_RANK() OVER( ORDER BY %s) ) AS jrank
           FROM %s
   )
       SELECT *,
           MIN( %d * %s / jrank )
           OVER (
               ORDER BY jrank DESC
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS p_adj
       FROM ranked_data
   )
   SELECT * EXCEPT (p_adj, jrank), IF( p_adj > 1.0 , 1.0, p_adj) AS p_adj
   FROM padjusted_data
   ORDER BY jrank""", pvalue_column_name, pvalue_table_name, n_rows, pvalue_column_name );
END;

-- a unit test of bh_multiple_tests
BEGIN

   CREATE TEMP TABLE Pvalues AS
      SELECT 0.001 as pval
      UNION ALL SELECT 0.008
      UNION ALL SELECT 0.039
      UNION ALL SELECT 0.041
      UNION ALL SELECT 0.042
      UNION ALL SELECT 0.06
      UNION ALL SELECT 0.074
      UNION ALL SELECT 0.205;

   CALL bqutil.procedure.bh_multiple_tests('Pvalues','pval',8);

   # Table Output
   # pval   p_adj
   # 0.001  0.008
   # 0.008  0.032
   # 0.039  0.06720000000000001
   # 0.041  0.06720000000000001
   # 0.042  0.06720000000000001
   # 0.06  0.08
   # 0.074  0.08457142857142856
   # 0.205  0.205

   ASSERT(
       SELECT COUNTIF(
           (pval = 0.001 AND p_adj = 0.008)
           OR (pval = 0.008 AND p_adj = 0.032)
            OR (pval = 0.039 AND p_adj = 0.06720000000000001)
            OR (pval = 0.041 AND p_adj = 0.06720000000000001)
            OR (pval = 0.042 AND p_adj = 0.06720000000000001)
            OR (pval = 0.06 AND p_adj = 0.08)
            OR (pval = 0.074 AND p_adj = 0.08457142857142856)
            OR (pval = 0.205 AND p_adj = 0.205)
       )
       FROM bh_multiple_tests_results
   ) = 8;




END;


