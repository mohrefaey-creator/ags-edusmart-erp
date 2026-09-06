"""AGS AI: settings and the query audit log (SKILL sec. 28)."""

from doctype_builder import SYS, column, doctype, f, perm, readonly_perm, section

MODULE = "AGS AI"

FIN = "AGS Finance Manager"


def specs() -> list[tuple[dict, str | None]]:
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS AI Settings", MODULE,
		[
			section("sb_narration", "Narration"),
			f("enable_narration", "Check", "Use A Language Model To Phrase Answers",
			  default="0",
			  description=(
				  "Off by default. Every figure is computed from the ledger either "
				  "way; a model only rephrases a finished result and can never "
				  "query data or invent a number."
			  )),
			f("provider", "Select", "Provider",
			  options="Anthropic\nOpenAI-Compatible", default="Anthropic",
			  depends_on="enable_narration"),
			f("model", "Data", "Model", default="claude-sonnet-5",
			  depends_on="enable_narration"),
			column("cb_narration"),
			f("api_base", "Data", "API Base URL", depends_on="enable_narration",
			  description="Leave blank for the provider default."),
			f("api_key", "Password", "API Key", depends_on="enable_narration"),
			f("max_output_tokens", "Int", "Max Output Tokens", default="400",
			  depends_on="enable_narration"),

			section("sb_retention", "Audit Retention"),
			f("query_log_retention_days", "Int", "Keep Query Log For (days)",
			  default="180",
			  description=(
				  "The query log records who ran which analysis and under what "
				  "scope, including refusals. Refusals are the useful half: a run "
				  "of them is how you notice someone probing outside their scope."
			  )),
		],
		is_single=True,
		permissions=[perm(SYS), readonly_perm(FIN)],
	), None))

	out.append((doctype(
		"AGS AI Query Log", MODULE,
		[
			f("analyzer", "Data", "Analysis", reqd=1, in_list_view=1, search_index=1),
			f("asked_by", "Link", "Asked By", options="User", reqd=1, in_list_view=1,
			  search_index=1),
			f("permitted", "Check", "Permitted", default="1", in_list_view=1,
			  description="Unticked means the analysis was refused for this user."),
			section("sb_scope", "Scope Applied"),
			f("scope_description", "Small Text", "Scope"),
			f("company", "Link", "Company", options="Company"),
			column("cb_scope"),
			f("campuses", "Small Text", "Campuses"),
			f("unrestricted", "Check", "Group-Wide", default="0"),
		],
		autoname="hash",
		# Read-only to everyone including System Manager: an audit trail that the
		# audited party can edit is not an audit trail. Deletion happens only
		# through the retention job.
		permissions=[readonly_perm(SYS), readonly_perm("AGS Auditor"), readonly_perm(FIN)],
		sort_field="creation",
		track_changes=False,
		description="Who asked which analysis, under what scope. Includes refusals.",
	), None))

	return out
