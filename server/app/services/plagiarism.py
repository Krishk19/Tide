import ast
import re
import difflib
from datetime import datetime, timezone
from typing import List, Tuple, Set, Dict, Optional, Any
from sqlalchemy.orm import Session as DBSession

from app.models.entities import StudentInSession, Submission, CodeSnapshot, Flag, Session, Assignment

BUILTINS_PRESERVED = {
    'range', 'len', 'print', 'int', 'str', 'float', 'bool', 'list', 'dict', 'set',
    'tuple', 'sum', 'min', 'max', 'enumerate', 'zip', 'reversed', 'sorted', 'map',
    'filter', 'abs', 'round', 'open', 'input', 'append', 'extend', 'pop', 'insert',
    'remove', 'index', 'count', 'sort', 'reverse', 'strip', 'split', 'join', 'replace',
    'find', 'lower', 'upper', 'keys', 'values', 'items', 'get', 'math', 'sys', 'os',
    'collections', 'itertools', 'heapq', 'bisect', 'True', 'False', 'None'
}

CPP_JAVA_KEYWORDS = {
    'int', 'float', 'double', 'char', 'bool', 'void', 'long', 'short',
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'break', 'continue',
    'return', 'class', 'struct', 'public', 'private', 'protected', 'static',
    'const', 'auto', 'template', 'typename', 'include', 'import', 'package',
    'new', 'delete', 'try', 'catch', 'throw', 'throws', 'virtual', 'override',
    'final', 'abstract', 'interface', 'implements', 'extends', 'cin', 'cout',
    'vector', 'string', 'map', 'set', 'unordered_map', 'unordered_set', 'queue', 'stack',
    'select', 'from', 'where', 'join', 'group', 'by', 'order', 'having', 'insert', 'update', 'delete'
}


class PythonASTNormalizer(ast.NodeTransformer):
    """
    Transforms Python AST into canonical representation:
    1. Alpha-renames user variables, function names, and arguments (v0, v1, fn0, arg0).
    2. Strips docstrings and type annotations.
    3. Normalizes typed assignments to untyped assignments.
    """
    def __init__(self):
        super().__init__()
        self.var_map: Dict[str, str] = {}
        self.fn_map: Dict[str, str] = {}
        self.arg_map: Dict[str, str] = {}
        self.cls_map: Dict[str, str] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Strip docstrings if first statement is an Expr with Constant string
        if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(getattr(node.body[0], 'value', None), ast.Constant) and
                isinstance(node.body[0].value.value, str)):
            node.body.pop(0)

        # Alpha-rename function name if not preserved / magic
        if node.name not in BUILTINS_PRESERVED and not (node.name.startswith('__') and node.name.endswith('__')):
            if node.name not in self.fn_map:
                self.fn_map[node.name] = f"fn{len(self.fn_map)}"
            node.name = self.fn_map[node.name]

        # Strip return type annotations
        node.returns = None

        # Filter out standalone pass statements if there are other statements
        new_body = [stmt for stmt in node.body if not isinstance(stmt, ast.Pass)]
        if new_body:
            node.body = new_body

        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        return self.visit_FunctionDef(node)

    def visit_arg(self, node: ast.arg):
        node.annotation = None
        if node.arg not in ('self', 'cls'):
            if node.arg not in self.arg_map:
                self.arg_map[node.arg] = f"arg{len(self.arg_map)}"
            node.arg = self.arg_map[node.arg]
        return node

    def visit_ClassDef(self, node: ast.ClassDef):
        if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(getattr(node.body[0], 'value', None), ast.Constant) and
                isinstance(node.body[0].value.value, str)):
            node.body.pop(0)

        if node.name not in self.cls_map:
            self.cls_map[node.name] = f"cls{len(self.cls_map)}"
        node.name = self.cls_map[node.name]

        self.generic_visit(node)
        return node

    def visit_Name(self, node: ast.Name):
        if node.id not in BUILTINS_PRESERVED:
            if node.id in self.fn_map:
                node.id = self.fn_map[node.id]
            elif node.id in self.arg_map:
                node.id = self.arg_map[node.id]
            else:
                if node.id not in self.var_map:
                    self.var_map[node.id] = f"v{len(self.var_map)}"
                node.id = self.var_map[node.id]
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self.generic_visit(node)
        if node.value is not None:
            return ast.Assign(targets=[node.target], value=node.value)
        return None


def serialize_ast_to_tokens(node: ast.AST) -> List[str]:
    """Preorder traversal of AST emitting canonical syntactic tokens."""
    tokens = []

    def _traverse(curr):
        tokens.append(type(curr).__name__)
        if isinstance(curr, ast.Name):
            tokens.append(curr.id)
        elif isinstance(curr, (ast.FunctionDef, ast.AsyncFunctionDef)):
            tokens.append(curr.name)
        elif isinstance(curr, ast.arg):
            tokens.append(curr.arg)
        elif isinstance(curr, ast.Constant):
            if isinstance(curr.value, bool):
                tokens.append(f"BOOL_{curr.value}")
            elif curr.value is None:
                tokens.append("NONE")
            elif isinstance(curr.value, (int, float)):
                tokens.append("NUM")
            elif isinstance(curr.value, str):
                tokens.append("STR")
            else:
                tokens.append("CONST")

        for child in ast.iter_child_nodes(curr):
            _traverse(child)

    _traverse(node)
    return tokens


def tokenize_generic_code(code: str) -> List[str]:
    """Fallback tokenizer for C++, Java, SQL, or unparseable Python."""
    # Strip comments
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    # Strip literals
    code = re.sub(r'"([^"\\]|\\.)*"', ' STR_LIT ', code)
    code = re.sub(r"'([^'\\]|\\.)*'", ' CHAR_LIT ', code)

    # Token patterns
    token_pattern = re.compile(r'\b[A-Za-z_]\w*\b|\b\d+(\.\d+)?\b|[{}()\[\];,+\-*/%=!<>|&^~?:]+')
    raw_tokens = token_pattern.findall(code)

    var_map: Dict[str, str] = {}
    tokens = []
    for tok in raw_tokens:
        tok_lower = tok.lower()
        if tok_lower in CPP_JAVA_KEYWORDS:
            tokens.append(tok_lower)
        elif re.match(r'^\d+(\.\d+)?$', tok):
            tokens.append('NUM_LIT')
        elif re.match(r'^[A-Za-z_]\w*$', tok):
            if tok not in var_map:
                var_map[tok] = f"tok{len(var_map)}"
            tokens.append(var_map[tok])
        else:
            tokens.append(tok)
    return tokens


def tokenize_code(code: str, language: str = "python") -> List[str]:
    """Tokenizes code according to language, with AST for Python and regex fallback."""
    if not code or not code.strip():
        return []

    lang = (language or "python").lower()
    if lang == "python":
        try:
            tree = ast.parse(code)
            normalizer = PythonASTNormalizer()
            normalized_tree = normalizer.visit(tree)
            ast.fix_missing_locations(normalized_tree)
            return serialize_ast_to_tokens(normalized_tree)
        except Exception:
            # Fallback to generic tokenizer if syntax error exists in incomplete code
            return tokenize_generic_code(code)
    else:
        return tokenize_generic_code(code)


def generate_kgrams(tokens: List[str], k: int = 4) -> List[Tuple[str, ...]]:
    if not tokens:
        return []
    actual_k = min(k, len(tokens))
    if actual_k <= 0:
        return []
    return [tuple(tokens[i : i + actual_k]) for i in range(len(tokens) - actual_k + 1)]


def compute_similarity(
    tokens_a: List[str],
    tokens_b: List[str],
    starter_tokens: Optional[List[str]] = None,
    k: int = 4
) -> Tuple[float, int, int]:
    """
    Computes structural similarity percentage, shared k-grams, and total unique k-grams.
    Optionally masks out boilerplate k-grams from starter_code.
    Formula: 60% k-gram Jaccard Index + 40% Token Sequence Alignment Ratio.
    """
    if not tokens_a or not tokens_b:
        return 0.0, 0, 0

    kgrams_a = set(generate_kgrams(tokens_a, k))
    kgrams_b = set(generate_kgrams(tokens_b, k))

    # Mask boilerplate starter code k-grams if present
    if starter_tokens:
        starter_kgrams = set(generate_kgrams(starter_tokens, k))
        kgrams_a = kgrams_a - starter_kgrams
        kgrams_b = kgrams_b - starter_kgrams

    if not kgrams_a or not kgrams_b:
        return 0.0, 0, max(len(kgrams_a), len(kgrams_b))

    intersection = kgrams_a.intersection(kgrams_b)
    union = kgrams_a.union(kgrams_b)

    jaccard = (len(intersection) / len(union)) if union else 0.0

    matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b)
    seq_ratio = matcher.ratio()

    score = (0.6 * jaccard + 0.4 * seq_ratio) * 100.0
    return round(score, 1), len(intersection), len(union)


def analyze_session_plagiarism(
    session_id: int,
    db: DBSession,
    threshold: float = 65.0
) -> Dict[str, Any]:
    """
    Computes all pairwise code similarities for students in a session.
    Correlates AST structural similarity with keystroke telemetry flags and timeline gaps.
    """
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        return {"error": "Session not found", "pairs": []}

    assignment = session.assignment
    starter_tokens = tokenize_code(assignment.starter_code or "", "python") if assignment and assignment.starter_code else None

    # Load all students and their latest code + flags
    students = db.query(StudentInSession).filter(StudentInSession.session_id == session_id).all()
    if len(students) < 2:
        return {
            "session_id": session_id,
            "assignment_title": assignment.title if assignment else "Exam",
            "total_students": len(students),
            "total_pairs_compared": 0,
            "flagged_pairs_count": 0,
            "threshold": threshold,
            "pairs": []
        }

    # Pre-extract data for each student
    student_records = []
    for st in students:
        sub = db.query(Submission).filter(Submission.student_session_id == st.id).first()
        code = ""
        lang = "python"
        submitted_at = None

        if sub and sub.code:
            code = sub.code
            lang = sub.language or "python"
            submitted_at = sub.submitted_at
        else:
            # Check latest snapshot
            snap = db.query(CodeSnapshot).filter(CodeSnapshot.student_session_id == st.id).order_by(CodeSnapshot.ts.desc()).first()
            if snap and snap.code:
                code = snap.code

        # Check telemetry flags
        flags = db.query(Flag).filter(Flag.student_session_id == st.id).all()
        has_paste = any(f.type == "paste" or f.type == "correlated-cheat-attempt" for f in flags)
        has_correlated = any(f.type == "correlated-cheat-attempt" for f in flags)

        tokens = tokenize_code(code, lang)
        student_records.append({
            "id": st.id,
            "name": st.student_name,
            "identifier": st.student_identifier,
            "risk_score": st.risk_score,
            "code": code,
            "language": lang,
            "tokens": tokens,
            "has_paste": has_paste,
            "has_correlated": has_correlated,
            "submitted_at": submitted_at
        })

    # Pairwise comparison
    pairs = []
    total_pairs = 0
    n = len(student_records)

    for i in range(n):
        for j in range(i + 1, n):
            total_pairs += 1
            st_a = student_records[i]
            st_b = student_records[j]

            # If either student wrote no code, skip or 0
            if not st_a["tokens"] or not st_b["tokens"]:
                continue

            sim_score, shared_k, total_k = compute_similarity(
                st_a["tokens"],
                st_b["tokens"],
                starter_tokens=starter_tokens,
                k=4
            )

            if sim_score >= threshold:
                tags = []
                if sim_score >= 90.0:
                    tags.append("Near-Identical AST Structure")
                elif sim_score >= 75.0:
                    tags.append("High Structural Similarity")

                if st_a["has_paste"] and st_b["has_paste"]:
                    tags.append("Both Exhibited Bulk Pastes")
                elif st_a["has_paste"] or st_b["has_paste"]:
                    tags.append("External Paste Spike")

                if st_a["has_correlated"] or st_b["has_correlated"]:
                    tags.append("Correlated Cheat Flag")

                if st_a["submitted_at"] and st_b["submitted_at"]:
                    diff_secs = abs((st_a["submitted_at"] - st_b["submitted_at"]).total_seconds())
                    if diff_secs <= 90:
                        tags.append(f"Synchronized Submission (Δt {int(diff_secs)}s)")

                if starter_tokens:
                    tags.append("Starter Template Subtracted")

                pairs.append({
                    "student_a": {
                        "id": st_a["id"],
                        "name": st_a["name"],
                        "identifier": st_a["identifier"],
                        "risk_score": st_a["risk_score"]
                    },
                    "student_b": {
                        "id": st_b["id"],
                        "name": st_b["name"],
                        "identifier": st_b["identifier"],
                        "risk_score": st_b["risk_score"]
                    },
                    "similarity_pct": sim_score,
                    "shared_kgrams": shared_k,
                    "total_kgrams": total_k,
                    "language": st_a["language"],
                    "correlation_tags": tags,
                    "is_suspicious": sim_score >= 75.0 or (sim_score >= 60.0 and (st_a["has_paste"] or st_b["has_paste"]))
                })

    # Sort descending by similarity
    pairs.sort(key=lambda p: p["similarity_pct"], reverse=True)

    return {
        "session_id": session_id,
        "assignment_title": assignment.title if assignment else "Exam",
        "total_students": len(students),
        "total_pairs_compared": total_pairs,
        "flagged_pairs_count": len(pairs),
        "threshold": threshold,
        "pairs": pairs
    }


def get_pairwise_diff(
    session_id: int,
    student_a_id: int,
    student_b_id: int,
    db: DBSession
) -> Dict[str, Any]:
    """Generates side-by-side diff payload and normalized tokens comparison."""
    st_a = db.query(StudentInSession).filter(StudentInSession.id == student_a_id, StudentInSession.session_id == session_id).first()
    st_b = db.query(StudentInSession).filter(StudentInSession.id == student_b_id, StudentInSession.session_id == session_id).first()

    if not st_a or not st_b:
        return {"error": "One or both students not found in this session"}

    sub_a = db.query(Submission).filter(Submission.student_session_id == st_a.id).first()
    sub_b = db.query(Submission).filter(Submission.student_session_id == st_b.id).first()

    code_a = sub_a.code if sub_a and sub_a.code else ""
    code_b = sub_b.code if sub_b and sub_b.code else ""
    lang_a = sub_a.language if sub_a and sub_a.language else "python"
    lang_b = sub_b.language if sub_b and sub_b.language else "python"

    tokens_a = tokenize_code(code_a, lang_a)
    tokens_b = tokenize_code(code_b, lang_b)

    session = db.query(Session).filter(Session.id == session_id).first()
    starter_tokens = None
    if session and session.assignment and session.assignment.starter_code:
        starter_tokens = tokenize_code(session.assignment.starter_code, "python")

    sim_score, shared_k, total_k = compute_similarity(tokens_a, tokens_b, starter_tokens=starter_tokens)

    # Compute text unified diff lines
    lines_a = code_a.splitlines(keepends=True)
    lines_b = code_b.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        lines_a, lines_b,
        fromfile=f"{st_a.student_name} ({st_a.student_identifier})",
        tofile=f"{st_b.student_name} ({st_b.student_identifier})",
        lineterm=""
    ))

    return {
        "session_id": session_id,
        "similarity_pct": sim_score,
        "shared_kgrams": shared_k,
        "total_kgrams": total_k,
        "student_a": {
            "id": st_a.id,
            "name": st_a.student_name,
            "identifier": st_a.student_identifier,
            "code": code_a,
            "language": lang_a,
            "line_count": len(code_a.splitlines()) if code_a else 0,
            "token_count": len(tokens_a)
        },
        "student_b": {
            "id": st_b.id,
            "name": st_b.student_name,
            "identifier": st_b.student_identifier,
            "code": code_b,
            "language": lang_b,
            "line_count": len(code_b.splitlines()) if code_b else 0,
            "token_count": len(tokens_b)
        },
        "diff_text": "".join(diff_lines),
        "normalized_tokens_sample_a": tokens_a[:60],
        "normalized_tokens_sample_b": tokens_b[:60]
    }
