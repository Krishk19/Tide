import re
import sqlite3
import time
from typing import Any, Optional
from collections import Counter
from dataclasses import dataclass

@dataclass
class SqlTestResult:
    test_id: Any
    passed: bool
    status: str  # "passed", "failed", "syntax_error", "execution_error"
    input_schema_summary: str
    student_rows_count: int
    expected_rows_count: int
    student_columns: list[str]
    expected_columns: list[str]
    sample_student_output: Optional[list[Any]] = None
    sample_expected_output: Optional[list[Any]] = None
    execution_time_ms: float = 0.0
    error: Optional[str] = None

def normalize_value(val: Any) -> Any:
    """Normalizes cell values for resilient comparison."""
    if val is None:
        return None
    if isinstance(val, float):
        return round(val, 4)
    if isinstance(val, str):
        return val.strip()
    return val

def normalize_row(row: tuple) -> tuple:
    """Normalizes a single database row tuple."""
    return tuple(normalize_value(v) for v in row)

def requires_order(query: str) -> bool:
    """Checks if query contains an explicit ORDER BY clause."""
    return bool(re.search(r"\border\s+by\b", query, re.IGNORECASE))

class SqlGrader:
    """
    Dedicated SQL grading pipeline with isolated in-memory SQLite instances
    and order-agnostic multiset result-set comparisons.
    """

    @staticmethod
    def evaluate_query(
        student_query: str,
        schema_seed: str,
        reference_query: str,
        test_id: Any = None,
        force_ordered: Optional[bool] = None
    ) -> SqlTestResult:
        """
        Executes student query and reference query against fresh in-memory SQLite instances.
        Normalizes and compares the resulting tables.
        """
        start_time = time.perf_counter()

        # 1. Setup Student Database Instance
        try:
            student_conn = sqlite3.connect(":memory:")
            student_cur = student_conn.cursor()
            student_cur.executescript(schema_seed)
        except Exception as ex:
            return SqlTestResult(
                test_id=test_id,
                passed=False,
                status="schema_error",
                input_schema_summary="Failed to initialize schema/seed data",
                student_rows_count=0,
                expected_rows_count=0,
                student_columns=[],
                expected_columns=[],
                error=f"Schema initialization error: {str(ex)}"
            )

        # 2. Setup Reference Database Instance
        ref_conn = sqlite3.connect(":memory:")
        ref_cur = ref_conn.cursor()
        ref_cur.executescript(schema_seed)

        # 3. Execute Reference Query
        try:
            ref_cur.execute(reference_query)
            ref_columns = [desc[0].lower() for desc in (ref_cur.description or [])]
            ref_raw_rows = ref_cur.fetchall()
            ref_rows = [normalize_row(r) for r in ref_raw_rows]
        except Exception as ex:
            student_conn.close()
            ref_conn.close()
            return SqlTestResult(
                test_id=test_id,
                passed=False,
                status="reference_error",
                input_schema_summary=schema_seed[:100],
                student_rows_count=0,
                expected_rows_count=0,
                student_columns=[],
                expected_columns=[],
                error=f"Instructor reference query error: {str(ex)}"
            )

        # 4. Execute Student Query
        try:
            student_cur.execute(student_query)
            student_columns = [desc[0].lower() for desc in (student_cur.description or [])]
            student_raw_rows = student_cur.fetchall()
            student_rows = [normalize_row(r) for r in student_raw_rows]
        except Exception as ex:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            student_conn.close()
            ref_conn.close()
            return SqlTestResult(
                test_id=test_id,
                passed=False,
                status="syntax_error",
                input_schema_summary=schema_seed[:100],
                student_rows_count=0,
                expected_rows_count=len(ref_rows),
                student_columns=[],
                expected_columns=ref_columns,
                execution_time_ms=elapsed_ms,
                error=f"SQL error: {str(ex)}"
            )
        finally:
            student_conn.close()
            ref_conn.close()

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Check Column Count
        if len(student_columns) != len(ref_columns):
            return SqlTestResult(
                test_id=test_id,
                passed=False,
                status="failed",
                input_schema_summary=schema_seed[:100],
                student_rows_count=len(student_rows),
                expected_rows_count=len(ref_rows),
                student_columns=student_columns,
                expected_columns=ref_columns,
                sample_student_output=student_rows[:5],
                sample_expected_output=ref_rows[:5],
                execution_time_ms=elapsed_ms,
                error=f"Column count mismatch: expected {len(ref_columns)} columns, got {len(student_columns)}"
            )

        # Determine Ordering Requirement
        is_ordered = force_ordered if force_ordered is not None else requires_order(reference_query)

        # 5. Compare Results
        if is_ordered:
            # Exact ordered sequence match
            passed = (student_rows == ref_rows)
        else:
            # Order-agnostic multiset comparison
            passed = (Counter(student_rows) == Counter(ref_rows))

        return SqlTestResult(
            test_id=test_id,
            passed=passed,
            status="passed" if passed else "failed",
            input_schema_summary=schema_seed[:100],
            student_rows_count=len(student_rows),
            expected_rows_count=len(ref_rows),
            student_columns=student_columns,
            expected_columns=ref_columns,
            sample_student_output=student_rows[:5],
            sample_expected_output=ref_rows[:5],
            execution_time_ms=elapsed_ms,
            error=None if passed else "Result rows do not match expected output"
        )
