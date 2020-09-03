//
// Copyright 2020 BigQuery Utils
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

#include "fix_column_not_grouped.h"

#include "absl/strings/str_cat.h"
#include "zetasql/parser/parser.h"
#include "zetasql_helper/util/util.h"


namespace bigquery::utils::zetasql_helper {


absl::Status
FixColumnNotGrouped(absl::string_view query, absl::string_view missing_column, int line_number, int column_number,
                    std::string* fixed_query) {

  std::unique_ptr<zetasql::ParserOutput> parser_output;
  auto options = BigQueryOptions();
  auto status = ParseStatement(query, options.GetParserOptions(), &parser_output);
  if (!status.ok()) {
    return status;
  }

  missing_column = remove_backtick(missing_column);

  auto offset = get_offset(query, line_number, column_number);
  if (offset == -1) {
    return absl::Status(absl::StatusCode::kInvalidArgument, "Line and/or column numbers are incorrect");
  }
  auto select_node = find_select_node_having_column(parser_output->statement(), offset, missing_column);
  if (select_node == nullptr) {
    return absl::Status(absl::StatusCode::kInvalidArgument, "Cannot locate the ungrouped column");
  }

  add_column_to_group_by_clause(
      const_cast<zetasql::ASTSelect*>(select_node),
      missing_column, parser_output->arena().get(),
      parser_output->id_string_pool().get()
  );

  *fixed_query = Unparse(parser_output->statement());
  return absl::OkStatus();
}

const zetasql::ASTSelect*
find_select_node_having_column(const zetasql::ASTStatement* statement, int column_start_offset,
                               absl::string_view column) {

  // Find the Column node starting at the given offset
  auto node = find_path_expression_node(*statement, column_start_offset, column);
  if (node == nullptr) {
    return nullptr;
  }

  // Find the parent Select node of the column node
  while (node != nullptr) {
    auto select_node = dynamic_cast<const zetasql::ASTSelect*>(node);
    if (select_node) {
      return select_node;
    }
    node = node->parent();
  }
  return nullptr;
}

const zetasql::ASTNode*
find_path_expression_node(const zetasql::ASTNode& node, int column_start_offset, absl::string_view name) {

  // Setup the predicator to find the target path expression node
  auto predicator = [column_start_offset](const zetasql::ASTNode* node) {
    return node->GetParseLocationRange().start().GetByteOffset() == column_start_offset &&
        node->node_kind() == zetasql::ASTNodeKind::AST_PATH_EXPRESSION;
  };

  auto candidate = find_node(&node, predicator);
  if (is_path_expression(candidate, name)) {
    return candidate;
  }
  return nullptr;
}

bool is_path_expression(const zetasql::ASTNode* node, absl::string_view name) {
  auto path_expression = dynamic_cast<const zetasql::ASTPathExpression*>(node);
  if (path_expression == nullptr) {
    return false;
  }

  // verify the node at this offset having the same name as input.
  return name == path_expression->last_name()->GetAsString();
}

void add_column_to_group_by_clause(
    zetasql::ASTSelect* select_node,
    absl::string_view column,
    zetasql_base::UnsafeArena* arena,
    zetasql::IdStringPool* id_string_pool
) {

  auto group_by = get_or_create_group_by_node(select_node, arena);
  auto item = new_grouping_column(column, arena, id_string_pool);

  group_by->AddChild(item);
  ((zetasql::ASTNode*) group_by)->InitFields();
}

zetasql::ASTGroupBy* get_or_create_group_by_node(
    zetasql::ASTSelect* select_node,
    zetasql_base::UnsafeArena* arena) {

  if (select_node->group_by() != nullptr) {
    return const_cast<zetasql::ASTGroupBy*>(select_node->group_by());
  }

  auto group_by_node = new(zetasql_base::AllocateInArena, arena) zetasql::ASTGroupBy;
  select_node->AddChild(group_by_node);
  ((zetasql::ASTNode*) select_node)->InitFields();
  return group_by_node;
}

zetasql::ASTGroupingItem* new_grouping_column(
    absl::string_view column,
    zetasql_base::UnsafeArena* arena,
    zetasql::IdStringPool* id_string_pool
) {

  // (grouping_item)->(path_expression)->(identifier)
  // Thus, we need to create the child first and assign it to the parent.

  auto identifier = new(zetasql_base::AllocateInArena, arena) zetasql::ASTIdentifier;
  identifier->SetIdentifier(id_string_pool->Make(column));
  ((zetasql::ASTNode*) identifier)->InitFields();

  auto pathExpression = new(zetasql_base::AllocateInArena, arena) zetasql::ASTPathExpression;
  pathExpression->AddChild(identifier);
  ((zetasql::ASTNode*) pathExpression)->InitFields();

  auto grouping_item = new(zetasql_base::AllocateInArena, arena) zetasql::ASTGroupingItem;
  grouping_item->AddChild(pathExpression);
  ((zetasql::ASTNode*) grouping_item)->InitFields();
  return grouping_item;
}

} //bigquery::utils::zetasql_helper



