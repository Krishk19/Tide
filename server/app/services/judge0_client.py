import httpx
from typing import Optional, Any
from app.core.config import settings
from app.services.sandbox import LocalSandbox, TestExecutionResult

# Judge0 standard language IDs
JUDGE0_LANGUAGE_IDS = {
    "python": 71,  # Python (3.8.1)
    "py": 71,
    "cpp": 54,     # C++ (GCC 9.2.0)
    "c++": 54,
    "c": 50,       # C (GCC 9.2.0)
    "java": 62,    # Java (OpenJDK 13.0.1)
}

class Judge0Client:
    """
    Client for self-hosted Judge0 instance in Docker.
    If Judge0 is unavailable or offline, seamlessly falls back to LocalSandbox.
    """

    @classmethod
    async def is_available(cls) -> bool:
        """Checks if the Judge0 service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(f"{settings.JUDGE0_URL}/system_info")
                return res.status_code == 200
        except Exception:
            return False

    @classmethod
    async def run_single_test(
        cls,
        language: str,
        code: str,
        stdin_data: str,
        expected_output: str,
        test_id: Any = None
    ) -> TestExecutionResult:
        lang_id = JUDGE0_LANGUAGE_IDS.get(language.lower().strip())
        if not lang_id:
            # Fall back to local runner if language ID not found
            return LocalSandbox.run_test_suite(language, code, [{"id": test_id, "input": stdin_data, "expected_output": expected_output}])[0]

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                payload = {
                    "source_code": code,
                    "language_id": lang_id,
                    "stdin": stdin_data,
                    "expected_output": expected_output
                }
                # Submit execution
                res = await client.post(
                    f"{settings.JUDGE0_URL}/submissions?wait=true&base64_encoded=false",
                    json=payload
                )
                if res.status_code in [200, 201]:
                    data = res.json()
                    status_id = data.get("status", {}).get("id")
                    # Judge0 status 3 = Accepted
                    passed = (status_id == 3)
                    actual_out = data.get("stdout") or ""
                    err = data.get("stderr") or data.get("compile_output")
                    time_s = float(data.get("time") or 0.0)

                    return TestExecutionResult(
                        test_id=test_id,
                        passed=passed,
                        status="passed" if passed else "failed",
                        input=stdin_data,
                        expected_output=expected_output,
                        actual_output=actual_out,
                        execution_time_ms=time_s * 1000.0,
                        error=err
                    )
        except Exception:
            # Judge0 unreachable or timed out -> Fall back to LocalSandbox
            pass

        # LocalSandbox fallback
        results = LocalSandbox.run_test_suite(
            language,
            code,
            [{"id": test_id, "input": stdin_data, "expected_output": expected_output}]
        )
        return results[0]
