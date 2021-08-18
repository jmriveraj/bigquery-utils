-- @param STRING table_name table (or subquery) that contains the data
-- @param STRING independent_var name of the column in our table that represents our independent variable
-- @param STRING dependent_var name of the column in our table that represents our dependent variable
-- @return STRUCT <FLOAT64 x, FLOAT64 dof, FLOAT64 p> x is the chi-square statistic, dof is degrees of freedom, p is the pvalue

CREATE OR REPLACE PROCEDURE bqutil.procedure.chi_square (table_name STRING, independent_var STRING, dependent_var STRING, OUT result STRUCT<x FLOAT64, dof FLOAT64, p FLOAT64> )
BEGIN
EXECUTE IMMEDIATE """
    WITH contingency_table AS (
        SELECT DISTINCT
            """ || independent_var || """ as independent_var,
            """ || dependent_var || """ as dependent_var,
            COUNT(*) OVER(PARTITION BY """ || independent_var || """, """ || dependent_var || """) as count,
            COUNT(*) OVER(PARTITION BY """ || independent_var || """) independent_total,
            COUNT(*) OVER(PARTITION BY """ || dependent_var || """) dependent_total,
            COUNT(*) OVER() as total
        FROM """ || table_name || """ AS t0
    ),
    expected_table AS (
        SELECT
            independent_var,
            dependent_var,
            independent_total * dependent_total / total as count
        FROM `contingency_table`
    ),
    output AS (
        SELECT
            SUM(POW(contingency_table.count - expected_table.count, 2) / expected_table.count) as x,
            (COUNT(DISTINCT contingency_table.independent_var) - 1)
                * (COUNT(DISTINCT contingency_table.dependent_var) - 1) AS dof
        FROM contingency_table
        INNER JOIN expected_table
            ON expected_table.independent_var = contingency_table.independent_var
            AND expected_table.dependent_var = contingency_table.dependent_var
    )
    SELECT STRUCT (x, dof, bqutil.fn.pvalue(x, dof) AS p) FROM output
""" INTO result;
END;

-- a unit test of chi_square
BEGIN
    DECLARE result STRUCT<x FLOAT64, dof FLOAT64, p FLOAT64>;

    CREATE TEMP TABLE categorical (animal STRING, toy STRING) AS
        SELECT 'dog' AS animal, 'ball' as toy
        UNION ALL SELECT 'dog', 'ball'
        UNION ALL SELECT 'dog', 'ball'
        UNION ALL SELECT 'dog', 'ball'
        UNION ALL SELECT 'dog', 'yarn'
        UNION ALL SELECT 'dog', 'yarn'
        UNION ALL SELECT 'cat', 'ball'
        UNION ALL SELECT 'cat', 'yarn'
        UNION ALL SELECT 'cat', 'yarn'
        UNION ALL SELECT 'cat', 'yarn'
        UNION ALL SELECT 'cat', 'yarn'
        UNION ALL SELECT 'cat', 'yarn'
        UNION ALL SELECT 'cat', 'yarn';

  CALL bqutil.procedure.chi_square('categorical', 'animal', 'toy', result);

  ASSERT result.x = 3.7452380952380966;
  ASSERT result.dof = 1;
  ASSERT result.p = 0.052958181867438725;
END;
