from typing import Any
from app.services.sandbox import LocalSandbox, TestExecutionResult
from app.services.sql_grader import SqlGrader, SqlTestResult

def evaluate_submission(
    language: str,
    code: str,
    test_cases: list[dict[str, Any]],
    timeout_seconds: float = 3.0
) -> list[dict[str, Any]]:
    """
    Unified evaluation dispatcher for Python, C++, Java, and SQL.
    Returns normalized dictionary results suitable for API responses.
    """
    lang = language.lower().strip()

    if lang == "sql":
        results = []
        for tc in test_cases:
            schema_seed = tc.get("schema_seed") or tc.get("input") or ""
            ref_query = tc.get("reference_query") or tc.get("expected_output") or ""
            tid = tc.get("id")

            sql_res: SqlTestResult = SqlGrader.evaluate_query(
                student_query=code,
                schema_seed=schema_seed,
                reference_query=ref_query,
                test_id=tid
            )
            results.append({
                "test_id": tid,
                "passed": sql_res.passed,
                "status": sql_res.status,
                "input": schema_seed[:200],
                "expected_output": f"{sql_res.expected_rows_count} rows" if ref_query else "",
                "actual_output": f"{sql_res.student_rows_count} rows" if sql_res.sample_student_output is not None else "",
                "execution_time_ms": sql_res.execution_time_ms,
                "error": sql_res.error
            })
        return results

    # Polyglot Algorithmic Code (Python, C++, Java)
    exec_results = LocalSandbox.run_test_suite(
        language=lang,
        code=code,
        test_cases=test_cases,
        timeout_seconds=timeout_seconds
    )
    return [
        {
            "test_id": r.test_id,
            "passed": r.passed,
            "status": r.status,
            "input": r.input,
            "expected_output": r.expected_output,
            "actual_output": r.actual_output,
            "execution_time_ms": r.execution_time_ms,
            "error": r.error
        }
        for r in exec_results
    ]
