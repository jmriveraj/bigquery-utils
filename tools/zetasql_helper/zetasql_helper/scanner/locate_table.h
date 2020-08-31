//
// Created by mepan on 8/24/20.
//

#ifndef ZETASQL_HELPER_ZETASQL_HELPER_LOCATION_LOCATE_TABLE_H_
#define ZETASQL_HELPER_ZETASQL_HELPER_LOCATION_LOCATE_TABLE_H_

#include "zetasql/public/parse_location.h"
#include "zetasql/parser/parse_tree.h"
#include "zetasql_helper/util/util.h"

namespace bigquery::utils::zetasql_helper {

// Find the ranges [start byte offset - end byte offset) of all occurrences of the tables
// meeting the table_name_regex. A table name is considered as [[project.]dataset.]table, and no
// backtick will be included even they exist in the original query.
//
// Therefore `a`.b.c => a.b.c, `b.c` => b.c
//
// Input is a SQL query and the regex to match table name. The found table ranges will be pushed back
// into the output vector. If an error occurs inside this function, a status with the error will be
// returned. Otherwise, a OKStatus will be returned.
absl::Status LocateTableRanges(
    absl::string_view query,
    absl::string_view table_regex,
    std::vector<zetasql::ParseLocationRange> &output);

} //bigquery::utils::zetasql_helper

#endif //ZETASQL_HELPER_ZETASQL_HELPER_LOCATION_LOCATE_TABLE_H_
