import pytest
from app.services.sandbox import LocalSandbox
from app.services.sql_grader import SqlGrader
from app.services.executor import evaluate_submission

def test_python_success():
    code = """
import sys
data = sys.stdin.read().split()
if data:
    a, b = int(data[0]), int(data[1])
    print(a + b)
"""
    test_cases = [
        {"id": "tc1", "input": "3 5", "expected_output": "8"},
        {"id": "tc2", "input": "-2 10", "expected_output": "8"},
        {"id": "tc3", "input": "0 0", "expected_output": "0"}
    ]
    results = LocalSandbox.run_test_suite("python", code, test_cases)
    assert len(results) == 3
    assert all(r.passed for r in results)
    assert all(r.status == "passed" for r in results)

def test_python_wrong_answer():
    code = "print(42)"
    test_cases = [{"id": "tc1", "input": "hello", "expected_output": "100"}]
    results = LocalSandbox.run_test_suite("python", code, test_cases)
    assert len(results) == 1
    assert not results[0].passed
    assert results[0].status == "failed"

def test_python_infinite_loop_timeout():
    # Must be killed by timeout without blocking the test runner
    code = """
while True:
    pass
"""
    test_cases = [{"id": "tc1", "input": "", "expected_output": "done"}]
    results = LocalSandbox.run_test_suite("python", code, test_cases, timeout_seconds=1.0)
    assert len(results) == 1
    assert not results[0].passed
    assert results[0].status == "timeout"
    assert "Time Limit Exceeded" in str(results[0].error)

def test_python_runtime_error():
    code = "x = 1 / 0"
    test_cases = [{"id": "tc1", "input": "", "expected_output": "1"}]
    results = LocalSandbox.run_test_suite("python", code, test_cases)
    assert len(results) == 1
    assert not results[0].passed
    assert results[0].status == "runtime_error"
    assert "ZeroDivisionError" in str(results[0].error)

def test_cpp_execution():
    code = """
#include <iostream>
using namespace std;
int main() {
    int a, b;
    if (cin >> a >> b) {
        cout << a * b << endl;
    }
    return 0;
}
"""
    test_cases = [
        {"id": "c1", "input": "4 5", "expected_output": "20"},
        {"id": "c2", "input": "-3 6", "expected_output": "-18"}
    ]
    results = LocalSandbox.run_test_suite("cpp", code, test_cases)
    assert len(results) == 2
    assert all(r.passed for r in results)

def test_java_execution():
    code = """
import java.util.Scanner;
public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        if (sc.hasNextInt()) {
            int a = sc.nextInt();
            int b = sc.nextInt();
            System.out.println(a - b);
        }
    }
}
"""
    test_cases = [
        {"id": "j1", "input": "10 4", "expected_output": "6"}
    ]
    results = LocalSandbox.run_test_suite("java", code, test_cases)
    assert len(results) == 1
    assert results[0].passed

def test_sql_order_agnostic_grading():
    schema_seed = """
    CREATE TABLE students (id INT PRIMARY KEY, name TEXT, gpa REAL);
    INSERT INTO students VALUES (1, 'Alice', 3.8), (2, 'Bob', 3.4), (3, 'Charlie', 3.9);
    """
    # Reference query returns in default insertion order: Charlie, Alice
    ref_query = "SELECT name, gpa FROM students WHERE gpa >= 3.5;"
    
    # Student query returns reversed order (e.g. ORDER BY id ASC vs DESC or no ORDER BY)
    student_query = "SELECT name, gpa FROM students WHERE gpa >= 3.5 ORDER BY gpa ASC;"
    
    # Since reference query does not contain ORDER BY, multiset comparison should PASS!
    res = SqlGrader.evaluate_query(student_query, schema_seed, ref_query)
    assert res.passed
    assert res.status == "passed"
    assert res.student_rows_count == 2
    assert res.expected_rows_count == 2

def test_sql_ordered_grading():
    schema_seed = """
    CREATE TABLE leaderboard (user TEXT, score INT);
    INSERT INTO leaderboard VALUES ('player1', 50), ('player2', 90), ('player3', 75);
    """
    # Reference query HAS ORDER BY
    ref_query = "SELECT user, score FROM leaderboard ORDER BY score DESC;"
    
    # Student query without DESC (wrong order)
    student_wrong_order = "SELECT user, score FROM leaderboard ORDER BY score ASC;"
    res_wrong = SqlGrader.evaluate_query(student_wrong_order, schema_seed, ref_query)
    assert not res_wrong.passed
    assert res_wrong.status == "failed"

    # Student query with correct order
    student_correct_order = "SELECT user, score FROM leaderboard ORDER BY score DESC;"
    res_correct = SqlGrader.evaluate_query(student_correct_order, schema_seed, ref_query)
    assert res_correct.passed

def test_sql_syntax_error():
    schema_seed = "CREATE TABLE dummy (x INT);"
    ref_query = "SELECT x FROM dummy;"
    student_broken = "SELECCT non_existent FROM dummy"
    res = SqlGrader.evaluate_query(student_broken, schema_seed, ref_query)
    assert not res.passed
    assert res.status == "syntax_error"
    assert "syntax error" in str(res.error).lower() or "no such column" in str(res.error).lower()

def test_unified_executor():
    # Algorithmic Python
    py_cases = [{"id": 1, "input": "5", "expected_output": "25"}]
    py_res = evaluate_submission("python", "import sys; n = int(sys.stdin.read()); print(n*n)", py_cases)
    assert len(py_res) == 1
    assert py_res[0]["passed"]

    # SQL Dispatch
    sql_cases = [{
        "id": "sql1",
        "schema_seed": "CREATE TABLE items (name TEXT); INSERT INTO items VALUES ('A'), ('B');",
        "reference_query": "SELECT * FROM items;"
    }]
    sql_res = evaluate_submission("sql", "SELECT * FROM items;", sql_cases)
    assert len(sql_res) == 1
    assert sql_res[0]["passed"]
