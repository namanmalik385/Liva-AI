import json


def build_report_analysis_request(analysis_context):
    """Ask the model for narrative text, never calculated medical values."""
    context_json = json.dumps(
        analysis_context,
        ensure_ascii=True,
        separators=(",", ":"),
    )

    return f"""
You are a patient-friendly liver report explanation assistant.

Use only the current report data in CURRENT_ANALYSIS.
The previous report has already been reduced to deterministic trend strings.
Do not infer, calculate, replace, or modify any values, statuses, trends,
health scores, or risk levels.
Do not invent information for biomarkers whose value is null.
Do not diagnose a condition or claim that a result rules out disease.

For every biomarker with a non-null value, return one short explanation that:
- refers to its current status;
- mentions its trend only when a trend is available;
- uses cautious, patient-friendly language;
- recommends clinical review when its status is elevated, low, positive,
  abnormal, or borderline.

Also return a concise 2-4 sentence overall summary using only the supplied
current values, deterministic statuses, and trends.

CURRENT_ANALYSIS:
{context_json}

Respond with only this raw JSON shape:
{{
  "biomarker_insights": {{
    "<biomarker key>": "<one short insight>"
  }},
  "ai_summary": "<2-4 sentence summary>"
}}
"""
