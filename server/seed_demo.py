"""
Tide Demo Database Seeder
Pre-seeds the database with demo instructor accounts, algorithmic and SQL problems,
and ready-to-test sessions for instant evaluation and demo.
"""
from datetime import datetime, timedelta, timezone
from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models.entities import Teacher, Assignment, Session as ExamSession

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Create Instructor: Prof. Sharma
        teacher = db.query(Teacher).filter(Teacher.username == "prof_sharma").first()
        if not teacher:
            teacher = Teacher(
                username="prof_sharma",
                password_hash=hash_password("securepassword123"),
                name="Prof. R. K. Sharma"
            )
            db.add(teacher)
            db.commit()
            db.refresh(teacher)
            print(f"[+] Created Instructor: {teacher.name} (username: prof_sharma, password: securepassword123)")
        else:
            print(f"[i] Instructor prof_sharma already exists (ID: {teacher.id})")

        # 2. Create Assignment 1: Two Sum / Array Square
        assign1 = db.query(Assignment).filter(Assignment.title == "Square of an Integer").first()
        if not assign1:
            assign1 = Assignment(
                teacher_id=teacher.id,
                title="Square of an Integer",
                problem_statement="Read a single integer from standard input and print its square to standard output.\n\nInput Format:\nA single integer N (-1000 <= N <= 1000)\n\nOutput Format:\nPrint N * N.",
                starter_code="import sys\n\n# Read integer from stdin\nline = sys.stdin.read().strip()\nif line:\n    n = int(line)\n    print(n * n)\n",
                language_set="python,cpp,java",
                visible_test_cases=[
                    {"id": "v1", "input": "4", "expected_output": "16"},
                    {"id": "v2", "input": "-3", "expected_output": "9"}
                ],
                hidden_test_cases=[
                    {"id": "h1", "input": "0", "expected_output": "0"},
                    {"id": "h2", "input": "12", "expected_output": "144"},
                    {"id": "h3", "input": "-25", "expected_output": "625"}
                ]
            )
            db.add(assign1)
            db.commit()
            db.refresh(assign1)
            print(f"[+] Created Assignment 1: {assign1.title}")

        # 3. Create Assignment 2: SQL Department Query
        assign2 = db.query(Assignment).filter(Assignment.title == "Department High Earners (SQL)").first()
        if not assign2:
            schema_sql = """
            CREATE TABLE employees (id INT, name TEXT, department TEXT, salary REAL);
            INSERT INTO employees VALUES
                (1, 'Alice', 'Engineering', 95000),
                (2, 'Bob', 'Marketing', 62000),
                (3, 'Charlie', 'Engineering', 105000),
                (4, 'Diana', 'Sales', 58000),
                (5, 'Evan', 'Engineering', 88000);
            """
            assign2 = Assignment(
                teacher_id=teacher.id,
                title="Department High Earners (SQL)",
                problem_statement="Write a SQL query to find the names and salaries of all employees in the 'Engineering' department earning more than 90,000.\n\nColumns required: name, salary.",
                starter_code="-- Write your SQL query here\nSELECT name, salary FROM employees WHERE ...;",
                language_set="sql",
                visible_test_cases=[
                    {
                        "id": "v1",
                        "schema_seed": schema_sql,
                        "reference_query": "SELECT name, salary FROM employees WHERE department = 'Engineering' AND salary > 90000;"
                    }
                ],
                hidden_test_cases=[
                    {
                        "id": "h1",
                        "schema_seed": schema_sql + "INSERT INTO employees VALUES (6, 'Frank', 'Engineering', 120000);",
                        "reference_query": "SELECT name, salary FROM employees WHERE department = 'Engineering' AND salary > 90000;"
                    }
                ]
            )
            db.add(assign2)
            db.commit()
            db.refresh(assign2)
            print(f"[+] Created Assignment 2: {assign2.title}")

        # 4. Create Active Session: TIDE01 (Live right now)
        sess1 = db.query(ExamSession).filter(ExamSession.access_code == "TIDE01").first()
        now = datetime.now(timezone.utc)
        if not sess1:
            sess1 = ExamSession(
                teacher_id=teacher.id,
                assignment_id=assign1.id,
                access_code="TIDE01",
                start_time=now - timedelta(minutes=5),  # Started 5 mins ago -> Active!
                status="active"
            )
            db.add(sess1)
            db.commit()
            print("[+] Created Active Session: Access Code -> TIDE01 (Active right now)")

        # 5. Create Scheduled Session: TIDE02 (Starts in 45 seconds for Countdown Lock demo)
        sess2 = db.query(ExamSession).filter(ExamSession.access_code == "TIDE02").first()
        if not sess2:
            sess2 = ExamSession(
                teacher_id=teacher.id,
                assignment_id=assign1.id,
                access_code="TIDE02",
                start_time=now + timedelta(seconds=45),  # Starts in 45s -> Countdown Demo!
                status="scheduled"
            )
            db.add(sess2)
            db.commit()
            print("[+] Created Scheduled Session: Access Code -> TIDE02 (Starts in 45s for Countdown Demo)")

        print("\n=======================================================")
        print(" DEMO ENVIRONMENT SEEDED SUCCESSFULLY!")
        print("=======================================================")
        print(" Instructor Login : http://localhost:8000/dashboard")
        print("   Username       : prof_sharma")
        print("   Password       : securepassword123")
        print(" Student Portal   : http://localhost:8000/student")
        print("   Active Code    : TIDE01 (Instant access)")
        print("   Countdown Code : TIDE02 (Demonstrates countdown lock)")
        print(" API Docs (Swagger): http://localhost:8000/docs")
        print("=======================================================\n")

    finally:
        db.close()

if __name__ == "__main__":
    seed()
