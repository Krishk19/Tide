import os
import re
import sys
import time
import tempfile
import subprocess
from typing import Optional, Any
from dataclasses import dataclass

MAX_OUTPUT_LENGTH = 100_000  # 100 KB max stdout capture to avoid memory exhaustion
DEFAULT_TIMEOUT_SECONDS = 3.0
COMPILE_TIMEOUT_SECONDS = 10.0

@dataclass
class TestExecutionResult:
    test_id: Any
    passed: bool
    status: str  # "passed", "failed", "timeout", "compilation_error", "runtime_error"
    input: str
    expected_output: str
    actual_output: str
    execution_time_ms: float
    error: Optional[str] = None

def normalize_output(text: Optional[str]) -> str:
    """Normalizes line endings and strips trailing line whitespace."""
    if text is None:
        return ""
    # Normalize CRLF to LF
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip trailing whitespace on each line, and strip leading/trailing blank lines
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()

def kill_process_tree(pid: int):
    """Kills process and all its children on Windows/Unix."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0
            )
        else:
            os.killpg(os.getpgid(pid), 9)
    except Exception:
        pass

class LocalSandbox:
    """
    Sandboxed local runner for Python, C++, and Java.
    Executes student submissions against test cases with hard timeouts,
    isolated temp directories, and process tree termination.
    """

    @staticmethod
    def execute_python_test(
        code: str,
        stdin_data: str,
        expected_output: str,
        test_id: Any = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ) -> TestExecutionResult:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "solution.py")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            start_time = time.perf_counter()
            proc = None
            try:
                proc = subprocess.Popen(
                    [sys.executable, file_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=temp_dir
                )
                stdout_bytes, stderr_bytes = proc.communicate(
                    input=stdin_data.encode("utf-8"),
                    timeout=timeout_seconds
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                actual_stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_LENGTH]
                actual_stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_LENGTH]

                if proc.returncode != 0:
                    return TestExecutionResult(
                        test_id=test_id,
                        passed=False,
                        status="runtime_error",
                        input=stdin_data,
                        expected_output=expected_output,
                        actual_output=actual_stdout,
                        execution_time_ms=elapsed_ms,
                        error=actual_stderr.strip() or f"Process exited with code {proc.returncode}"
                    )

                norm_actual = normalize_output(actual_stdout)
                norm_expected = normalize_output(expected_output)
                passed = (norm_actual == norm_expected)

                return TestExecutionResult(
                    test_id=test_id,
                    passed=passed,
                    status="passed" if passed else "failed",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output=actual_stdout,
                    execution_time_ms=elapsed_ms,
                    error=None
                )

            except subprocess.TimeoutExpired:
                if proc:
                    kill_process_tree(proc.pid)
                elapsed_ms = timeout_seconds * 1000.0
                return TestExecutionResult(
                    test_id=test_id,
                    passed=False,
                    status="timeout",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output="",
                    execution_time_ms=elapsed_ms,
                    error=f"Time Limit Exceeded ({timeout_seconds}s)"
                )
            except Exception as ex:
                if proc:
                    kill_process_tree(proc.pid)
                return TestExecutionResult(
                    test_id=test_id,
                    passed=False,
                    status="runtime_error",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output="",
                    execution_time_ms=0.0,
                    error=str(ex)
                )

    @staticmethod
    def execute_cpp_test(
        code: str,
        stdin_data: str,
        expected_output: str,
        test_id: Any = None,
        compiled_exe_path: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ) -> TestExecutionResult:
        with tempfile.TemporaryDirectory() as temp_dir:
            exe_path = compiled_exe_path
            if not exe_path or not os.path.exists(exe_path):
                src_path = os.path.join(temp_dir, "solution.cpp")
                exe_path = os.path.join(temp_dir, "solution.exe" if sys.platform == "win32" else "solution")
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(code)

                # Compile with g++
                compile_proc = subprocess.run(
                    ["g++", "-O2", src_path, "-o", exe_path],
                    capture_output=True,
                    text=True,
                    timeout=COMPILE_TIMEOUT_SECONDS,
                    cwd=temp_dir
                )
                if compile_proc.returncode != 0:
                    return TestExecutionResult(
                        test_id=test_id,
                        passed=False,
                        status="compilation_error",
                        input=stdin_data,
                        expected_output=expected_output,
                        actual_output="",
                        execution_time_ms=0.0,
                        error=compile_proc.stderr[:MAX_OUTPUT_LENGTH]
                    )

            # Execute compiled binary
            start_time = time.perf_counter()
            proc = None
            try:
                proc = subprocess.Popen(
                    [exe_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=temp_dir
                )
                stdout_bytes, stderr_bytes = proc.communicate(
                    input=stdin_data.encode("utf-8"),
                    timeout=timeout_seconds
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                actual_stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_LENGTH]
                actual_stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_LENGTH]

                if proc.returncode != 0:
                    return TestExecutionResult(
                        test_id=test_id,
                        passed=False,
                        status="runtime_error",
                        input=stdin_data,
                        expected_output=expected_output,
                        actual_output=actual_stdout,
                        execution_time_ms=elapsed_ms,
                        error=actual_stderr.strip() or f"Process exited with code {proc.returncode}"
                    )

                norm_actual = normalize_output(actual_stdout)
                norm_expected = normalize_output(expected_output)
                passed = (norm_actual == norm_expected)

                return TestExecutionResult(
                    test_id=test_id,
                    passed=passed,
                    status="passed" if passed else "failed",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output=actual_stdout,
                    execution_time_ms=elapsed_ms,
                    error=None
                )
            except subprocess.TimeoutExpired:
                if proc:
                    kill_process_tree(proc.pid)
                return TestExecutionResult(
                    test_id=test_id,
                    passed=False,
                    status="timeout",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output="",
                    execution_time_ms=timeout_seconds * 1000.0,
                    error=f"Time Limit Exceeded ({timeout_seconds}s)"
                )

    @staticmethod
    def execute_java_test(
        code: str,
        stdin_data: str,
        expected_output: str,
        test_id: Any = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ) -> TestExecutionResult:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract public class name if student defined one, else use Solution
            match = re.search(r"public\s+class\s+([A-Za-z0-9_]+)", code)
            class_name = match.group(1) if match else "Solution"

            src_path = os.path.join(temp_dir, f"{class_name}.java")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Compile with javac
            compile_proc = subprocess.run(
                ["javac", src_path],
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT_SECONDS,
                cwd=temp_dir
            )
            if compile_proc.returncode != 0:
                return TestExecutionResult(
                    test_id=test_id,
                    passed=False,
                    status="compilation_error",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output="",
                    execution_time_ms=0.0,
                    error=compile_proc.stderr[:MAX_OUTPUT_LENGTH]
                )

            # Execute with java
            start_time = time.perf_counter()
            proc = None
            try:
                proc = subprocess.Popen(
                    ["java", class_name],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=temp_dir
                )
                stdout_bytes, stderr_bytes = proc.communicate(
                    input=stdin_data.encode("utf-8"),
                    timeout=timeout_seconds
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                actual_stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_LENGTH]
                actual_stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_LENGTH]

                if proc.returncode != 0:
                    return TestExecutionResult(
                        test_id=test_id,
                        passed=False,
                        status="runtime_error",
                        input=stdin_data,
                        expected_output=expected_output,
                        actual_output=actual_stdout,
                        execution_time_ms=elapsed_ms,
                        error=actual_stderr.strip() or f"Process exited with code {proc.returncode}"
                    )

                norm_actual = normalize_output(actual_stdout)
                norm_expected = normalize_output(expected_output)
                passed = (norm_actual == norm_expected)

                return TestExecutionResult(
                    test_id=test_id,
                    passed=passed,
                    status="passed" if passed else "failed",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output=actual_stdout,
                    execution_time_ms=elapsed_ms,
                    error=None
                )
            except subprocess.TimeoutExpired:
                if proc:
                    kill_process_tree(proc.pid)
                return TestExecutionResult(
                    test_id=test_id,
                    passed=False,
                    status="timeout",
                    input=stdin_data,
                    expected_output=expected_output,
                    actual_output="",
                    execution_time_ms=timeout_seconds * 1000.0,
                    error=f"Time Limit Exceeded ({timeout_seconds}s)"
                )

    @classmethod
    def run_test_suite(
        cls,
        language: str,
        code: str,
        test_cases: list[dict[str, Any]],
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ) -> list[TestExecutionResult]:
        """
        Executes code against a collection of test cases.
        """
        lang = language.lower().strip()
        results: list[TestExecutionResult] = []

        # For C++, compile once if possible to save compilation overhead
        compiled_exe: Optional[str] = None
        temp_dir_obj = None

        try:
            if lang in ["cpp", "c++", "c"]:
                temp_dir_obj = tempfile.TemporaryDirectory()
                src_path = os.path.join(temp_dir_obj.name, "solution.cpp")
                compiled_exe = os.path.join(temp_dir_obj.name, "solution.exe" if sys.platform == "win32" else "solution")
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(code)

                comp = subprocess.run(
                    ["g++", "-O2", src_path, "-o", compiled_exe],
                    capture_output=True,
                    text=True,
                    timeout=COMPILE_TIMEOUT_SECONDS,
                    cwd=temp_dir_obj.name
                )
                if comp.returncode != 0:
                    # Compilation error across all tests
                    for tc in test_cases:
                        results.append(TestExecutionResult(
                            test_id=tc.get("id"),
                            passed=False,
                            status="compilation_error",
                            input=str(tc.get("input", "")),
                            expected_output=str(tc.get("expected_output", "")),
                            actual_output="",
                            execution_time_ms=0.0,
                            error=comp.stderr[:MAX_OUTPUT_LENGTH]
                        ))
                    return results

            for tc in test_cases:
                tid = tc.get("id")
                stdin_data = str(tc.get("input", ""))
                expected_out = str(tc.get("expected_output", ""))

                if lang in ["python", "py"]:
                    res = cls.execute_python_test(code, stdin_data, expected_out, test_id=tid, timeout_seconds=timeout_seconds)
                elif lang in ["cpp", "c++", "c"]:
                    res = cls.execute_cpp_test(code, stdin_data, expected_out, test_id=tid, compiled_exe_path=compiled_exe, timeout_seconds=timeout_seconds)
                elif lang in ["java"]:
                    res = cls.execute_java_test(code, stdin_data, expected_out, test_id=tid, timeout_seconds=timeout_seconds)
                else:
                    res = TestExecutionResult(
                        test_id=tid,
                        passed=False,
                        status="unsupported_language",
                        input=stdin_data,
                        expected_output=expected_out,
                        actual_output="",
                        execution_time_ms=0.0,
                        error=f"Unsupported language: {language}"
                    )
                results.append(res)
        finally:
            if temp_dir_obj:
                temp_dir_obj.cleanup()

        return results
