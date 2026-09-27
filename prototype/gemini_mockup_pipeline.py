"""
NO NORMATIVO — prototipo heredado, fuera del alcance de este repositorio.

Origen: mockup generado por un agente de Google Gemini a partir de las referencias
bibliográficas de `DI_PF_TFI_ENTREGA1_v5.pdf` (ver la declaración de uso de IA
generativa dentro de ese documento), no producto del proceso SDD de este repositorio.

Este archivo NO representa la arquitectura objetivo de C-1/C-2/C-3 (ver specs/mission.md
§1-§2 y specs/tech-stack.md). Se conserva solo como referencia histórica del diseño
inicial. Contradice reglas vigentes del proyecto:
- Ejecuta código con `exec()` sin sandbox (prohibido en specs/tech-stack.md §5).
- Simula el motor Haskell en Python en vez de invocarlo (C-1 debe ser Haskell real).
- Calcula pass@1 y agrega métricas (prohibido: eso pertenece a la etapa de
  investigación posterior, no a este repositorio).
No usar como base para C-1/C-2/C-3. No corregir sus bugs internos: reemplazar.

---
Computational Model Pipeline Prototype - Version 5 (v5)
Based on DI_PF_TFI_ENTREGA1_v5.pdf:
"Mitigación de incertidumbre probabilística en LLM aplicados a procesos determinísticos mediante cálculo lambda"

This module expands the experimental pipeline to include 3 experimental groups as defined in Section 8 of v5:
1. Treatment Group: Functional DSL (Simply Typed Lambda Calculus - STLC) with Haskell-like static typechecker & scope checker.
2. Baseline 1 (Control Libre): Direct unconstrained Python script execution.
3. Baseline 2 (Control Estructurado en Python): Python code with static analysis inspection (Python AST + MyPy-like static type checking).

Benchmarking incorporates the lambdaRepair (Zhang et al., 2026) error taxonomy:
- Category 1: Syntax & Structural Errors
- Category 2: Type & Scope Errors
- Category 3: Logical & Runtime Errors
"""

import ast
import json
import time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
import enum

# ==========================================
# 1. TAXONOMY & METRICS DEFINITIONS (lambdaRepair)
# ==========================================

class ErrorCategory(enum.Enum):
    SYNTAX_ERROR = "syntax_error"      # Category 1: Malformed AST or syntax
    TYPE_ERROR = "type_error"          # Category 2: Type mismatch in ADT/Lambda calculus
    LOGIC_ERROR = "logic_error"        # Category 3: Semantic/Runtime failure
    SUCCESS = "success"

@dataclass
class TestCase:
    id: str
    description: str
    category: ErrorCategory
    input_data: Dict[str, Any]
    expected_output: Any
    mock_llm_stlc_ast: Dict[str, Any]      # For Treatment (STLC DSL)
    mock_llm_python_code: str             # For Baseline 1 & Baseline 2

@dataclass
class ExecutionResult:
    test_id: str
    group: str                             # "Treatment_STLC_Haskell", "Baseline1_Python_Free", "Baseline2_Python_Structured"
    generated_correctly: bool
    intercepted_by_verifier: bool
    runtime_failed: bool
    passed_test: bool
    error_detected: Optional[str]
    latency_ms: float

# ==========================================
# 2. TREATMENT: STLC (Simply Typed Lambda Calculus) & ADT TYPECHECKER
# ==========================================

class STLCType(enum.Enum):
    INT = "Int"
    BOOL = "Bool"
    STRING = "String"

class STLCAChecker:
    """
    Simulates the Haskell-based formal validation engine for the Simply Typed Lambda Calculus (STLC) DSL.
    Audits type safety and variable scope statically before execution.
    """
    def __init__(self):
        # Initial Type Environment (Gamma) representing business domain entities
        self.env: Dict[str, STLCType] = {
            "credit_score": STLCType.INT,
            "monthly_income": STLCType.INT,
            "has_defaults": STLCType.BOOL,
            "customer_tier": STLCType.STRING
        }

    def typecheck(self, node: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[STLCType]]:
        try:
            node_type = node.get("type")
            if not node_type:
                return False, "STLC Error: Node missing 'type' annotation", None

            # Literals
            if node_type == "Literal":
                val = node.get("value")
                val_type = node.get("value_type")
                if val_type == "Int" and isinstance(val, int):
                    return True, None, STLCType.INT
                elif val_type == "Bool" and isinstance(val, bool):
                    return True, None, STLCType.BOOL
                elif val_type == "String" and isinstance(val, str):
                    return True, None, STLCType.STRING
                else:
                    return False, f"STLC Type Error: Literal '{val}' conflicts with declared type '{val_type}'", None

            # Variable Abstraction / Environment Lookup
            elif node_type == "Var":
                name = node.get("name")
                if name not in self.env:
                    return False, f"STLC Scope Error: Unbound variable '{name}' in environment", None
                return True, None, self.env[name]

            # Binary Applications (Operations)
            elif node_type == "BinaryOp":
                op = node.get("op")
                left = node.get("left")
                right = node.get("right")

                ok_l, err_l, type_l = self.typecheck(left)
                if not ok_l: return False, err_l, None

                ok_r, err_r, type_r = self.typecheck(right)
                if not ok_r: return False, err_r, None

                if op in [">", "<", ">=", "<=", "=="]:
                    if type_l != type_r:
                        return False, f"STLC Type Mismatch in '{op}': Cannot compare {type_l.value} with {type_r.value}", None
                    return True, None, STLCType.BOOL
                elif op in ["AND", "OR"]:
                    if type_l != STLCType.BOOL or type_r != STLCType.BOOL:
                        return False, f"STLC Type Error in '{op}': Both operands must be Bool, got {type_l.value} and {type_r.value}", None
                    return True, None, STLCType.BOOL

            # Lambda Expression / Conditional (IfThenElse)
            elif node_type == "IfThenElse":
                cond = node.get("condition")
                then_b = node.get("then")
                else_b = node.get("else")

                ok_c, err_c, type_c = self.typecheck(cond)
                if not ok_c: return False, err_c, None
                if type_c != STLCType.BOOL:
                    return False, f"STLC Type Error: Guard condition must be Bool, got {type_c.value}", None

                ok_t, err_t, type_t = self.typecheck(then_b)
                if not ok_t: return False, err_t, None

                ok_e, err_e, type_e = self.typecheck(else_b)
                if not ok_e: return False, err_e, None

                if type_t != type_e:
                    return False, f"STLC Type Branch Error: 'then' branch ({type_t.value}) and 'else' branch ({type_e.value}) type mismatch", None

                return True, None, type_t

            return False, f"STLC Syntax Error: Unknown node constructor '{node_type}'", None

        except Exception as e:
            return False, f"STLC Validation Exception: {str(e)}", None

class STLCExecutor:
    """Evaluates a well-typed STLC AST deterministically."""
    def eval(self, node: Dict[str, Any], env: Dict[str, Any]) -> Any:
        ntype = node["type"]
        if ntype == "Literal":
            return node["value"]
        elif ntype == "Var":
            return env[node["name"]]
        elif ntype == "BinaryOp":
            op = node["op"]
            l = self.eval(node["left"], env)
            r = self.eval(node["right"], env)
            if op == ">": return l > r
            elif op == "<": return l < r
            elif op == "==": return l == r
            elif op == "AND": return l and r
            elif op == "OR": return l or r
        elif ntype == "IfThenElse":
            cond = self.eval(node["condition"], env)
            if cond:
                return self.eval(node["then"], env)
            else:
                return self.eval(node["else"], env)
        raise ValueError(f"Unknown AST node: {ntype}")

# ==========================================
# 3. BASELINE 2: PYTHON STRUCTURED STATIC ANALYZER (AST + Type Inspector)
# ==========================================

class PythonStaticAnalyzer:
    """
    Simulates Baseline 2 (Control Estructurado en Python).
    Uses Python's native `ast` module and type/scope checkers (MyPy-style) to validate Python code before execution.
    """
    def __init__(self):
        self.known_vars = {"credit_score": int, "monthly_income": int, "has_defaults": bool, "customer_tier": str}

    def validate_code(self, code_str: str) -> Tuple[bool, Optional[str]]:
        # 1. Syntax Check via AST parsing
        try:
            parsed_ast = ast.parse(code_str)
        except SyntaxError as e:
            return False, f"Python Syntax Error: {e.msg} at line {e.lineno}"

        # 2. Basic Static Type & Scope Inspector
        class RuleVisitor(ast.NodeVisitor):
            def __init__(self, outer):
                self.outer = outer
                self.error = None

            def visit_Subscript(self, node):
                # Inspect data['variable_name'] accesses
                if isinstance(node.slice, ast.Constant):
                    var_name = node.slice.value
                    if isinstance(var_name, str) and var_name not in self.outer.known_vars:
                        self.error = f"Python Scope Error (Static): Access to undefined dictionary key '{var_name}'"
                self.generic_visit(node)

            def visit_Compare(self, node):
                # Basic MyPy-like check for explicit type mismatches in comparison ops
                left = node.left
                for comparator in node.comparators:
                    if isinstance(left, ast.Subscript) and isinstance(comparator, ast.Constant):
                        if isinstance(left.slice, ast.Constant):
                            var_name = left.slice.value
                            expected_type = self.outer.known_vars.get(var_name)
                            const_val = comparator.value
                            if expected_type == int and isinstance(const_val, str):
                                self.error = f"Python Type Error (Static MyPy): Invalid comparison between int field '{var_name}' and str '{const_val}'"
                self.generic_visit(node)

        visitor = RuleVisitor(self)
        visitor.visit(parsed_ast)
        if visitor.error:
            return False, visitor.error

        return True, None

# ==========================================
# 4. BASELINE 1 & BASELINE 2 EXECUTORS
# ==========================================

class PythonExecutor:
    """Executes Python code dynamically."""
    def execute(self, code_str: str, input_data: Dict[str, Any]) -> Any:
        local_scope = {}
        exec(code_str, {}, local_scope)
        rule_fn = local_scope.get("evaluate_rule")
        if not rule_fn:
            raise RuntimeError("Missing required entrypoint function 'evaluate_rule'")
        return rule_fn(input_data)

# ==========================================
# 5. THREE-GROUP EXPERIMENTAL PIPELINE
# ==========================================

class ExperimentPipelineV5:
    def __init__(self):
        self.stlc_checker = STLCAChecker()
        self.stlc_executor = STLCExecutor()
        self.python_analyzer = PythonStaticAnalyzer()
        self.python_executor = PythonExecutor()

    def run_treatment(self, test: TestCase) -> ExecutionResult:
        """Group 1: Treatment (Functional DSL in STLC/Haskell)."""
        t0 = time.perf_counter()
        ast_json = test.mock_llm_stlc_ast

        # Static Typechecking
        is_valid, err_msg, _ = self.stlc_checker.typecheck(ast_json)
        latency = (time.perf_counter() - t0) * 1000.0

        if not is_valid:
            return ExecutionResult(
                test_id=test.id,
                group="Treatment_STLC_Haskell",
                generated_correctly=False,
                intercepted_by_verifier=True,
                runtime_failed=False,
                passed_test=False,
                error_detected=err_msg,
                latency_ms=latency
            )

        # Execution
        try:
            res = self.stlc_executor.eval(ast_json, test.input_data)
            passed = (res == test.expected_output)
            return ExecutionResult(
                test_id=test.id,
                group="Treatment_STLC_Haskell",
                generated_correctly=True,
                intercepted_by_verifier=False,
                runtime_failed=not passed,
                passed_test=passed,
                error_detected=None if passed else f"Logic Mismatch: Output={res}, Expected={test.expected_output}",
                latency_ms=latency
            )
        except Exception as e:
            return ExecutionResult(
                test_id=test.id,
                group="Treatment_STLC_Haskell",
                generated_correctly=False,
                intercepted_by_verifier=False,
                runtime_failed=True,
                passed_test=False,
                error_detected=f"Runtime Failure: {str(e)}",
                latency_ms=latency
            )

    def run_baseline_1(self, test: TestCase) -> ExecutionResult:
        """Group 2: Baseline 1 (Control Libre en Python, no static check)."""
        t0 = time.perf_counter()
        code = test.mock_llm_python_code

        try:
            res = self.python_executor.execute(code, test.input_data)
            latency = (time.perf_counter() - t0) * 1000.0
            passed = (res == test.expected_output)
            return ExecutionResult(
                test_id=test.id,
                group="Baseline1_Python_Free",
                generated_correctly=passed,
                intercepted_by_verifier=False,
                runtime_failed=not passed,
                passed_test=passed,
                error_detected=None if passed else f"Silent Logic Failure: Output={res}, Expected={test.expected_output}",
                latency_ms=latency
            )
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                test_id=test.id,
                group="Baseline1_Python_Free",
                generated_correctly=False,
                intercepted_by_verifier=False,
                runtime_failed=True,
                passed_test=False,
                error_detected=f"Dynamic Runtime Exception: {str(e)}",
                latency_ms=latency
            )

    def run_baseline_2(self, test: TestCase) -> ExecutionResult:
        """Group 3: Baseline 2 (Control Estructurado en Python, Python AST + MyPy)."""
        t0 = time.perf_counter()
        code = test.mock_llm_python_code

        # Static Analysis Layer
        is_valid, err_msg = self.python_analyzer.validate_code(code)
        latency_val = (time.perf_counter() - t0) * 1000.0

        if not is_valid:
            return ExecutionResult(
                test_id=test.id,
                group="Baseline2_Python_Structured",
                generated_correctly=False,
                intercepted_by_verifier=True,
                runtime_failed=False,
                passed_test=False,
                error_detected=err_msg,
                latency_ms=latency_val
            )

        # Dynamic Execution
        try:
            res = self.python_executor.execute(code, test.input_data)
            latency = (time.perf_counter() - t0) * 1000.0
            passed = (res == test.expected_output)
            return ExecutionResult(
                test_id=test.id,
                group="Baseline2_Python_Structured",
                generated_correctly=True,
                intercepted_by_verifier=False,
                runtime_failed=not passed,
                passed_test=passed,
                error_detected=None if passed else f"Silent Logic Failure: Output={res}, Expected={test.expected_output}",
                latency_ms=latency
            )
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                test_id=test.id,
                group="Baseline2_Python_Structured",
                generated_correctly=False,
                intercepted_by_verifier=False,
                runtime_failed=True,
                passed_test=False,
                error_detected=f"Dynamic Runtime Exception: {str(e)}",
                latency_ms=latency
            )

# ==========================================
# 6. BENCHMARK CORPUS (lambdaRepair Taxonomy)
# ==========================================

def get_v5_benchmark_corpus() -> List[TestCase]:
    return [
        # Case 1: Success / Valid Rule
        TestCase(
            id="RULE-001",
            description="Valid Rule: Credit Score > 700 AND no defaults",
            category=ErrorCategory.SUCCESS,
            input_data={"credit_score": 750, "monthly_income": 5000, "has_defaults": False, "customer_tier": "Gold"},
            expected_output=True,
            mock_llm_stlc_ast={
                "type": "BinaryOp", "op": "AND",
                "left": {"type": "BinaryOp", "op": ">", "left": {"type": "Var", "name": "credit_score"}, "right": {"type": "Literal", "value": 700, "value_type": "Int"}},
                "right": {"type": "BinaryOp", "op": "==", "left": {"type": "Var", "name": "has_defaults"}, "right": {"type": "Literal", "value": False, "value_type": "Bool"}}
            },
            mock_llm_python_code="""
def evaluate_rule(data):
    return data['credit_score'] > 700 and not data['has_defaults']
"""
        ),
        # Case 2: Type Error - Hallucinated Comparison (Int vs String)
        TestCase(
            id="RULE-002",
            description="Type Error: LLM compares Int field credit_score with String 'High'",
            category=ErrorCategory.TYPE_ERROR,
            input_data={"credit_score": 750, "monthly_income": 5000, "has_defaults": False, "customer_tier": "Gold"},
            expected_output=True,
            mock_llm_stlc_ast={
                "type": "BinaryOp", "op": ">",
                "left": {"type": "Var", "name": "credit_score"},
                "right": {"type": "Literal", "value": "High", "value_type": "String"}
            },
            mock_llm_python_code="""
def evaluate_rule(data):
    return data['credit_score'] > 'High'
"""
        ),
        # Case 3: Syntax/Structural Error - Branch Type Mismatch
        TestCase(
            id="RULE-003",
            description="Branch Type Error: Conditional returns Int on 'then' and String on 'else'",
            category=ErrorCategory.SYNTAX_ERROR,
            input_data={"credit_score": 650, "monthly_income": 5000, "has_defaults": False, "customer_tier": "Gold"},
            expected_output=100,
            mock_llm_stlc_ast={
                "type": "IfThenElse",
                "condition": {"type": "BinaryOp", "op": ">", "left": {"type": "Var", "name": "credit_score"}, "right": {"type": "Literal", "value": 700, "value_type": "Int"}},
                "then": {"type": "Literal", "value": 500, "value_type": "Int"},
                "else": {"type": "Literal", "value": "Rejected", "value_type": "String"}
            },
            mock_llm_python_code="""
def evaluate_rule(data):
    if data['credit_score'] > 700:
        return 500
    else:
        return "Rejected"
"""
        ),
        # Case 4: Scope / Type Error - Unbound Variable Access
        TestCase(
            id="RULE-004",
            description="Unbound Variable Error: LLM invents non-existent variable 'risk_level'",
            category=ErrorCategory.TYPE_ERROR,
            input_data={"credit_score": 750, "monthly_income": 5000, "has_defaults": False, "customer_tier": "Gold"},
            expected_output=True,
            mock_llm_stlc_ast={
                "type": "BinaryOp", "op": "==",
                "left": {"type": "Var", "name": "risk_level"},
                "right": {"type": "Literal", "value": "Low", "value_type": "String"}
            },
            mock_llm_python_code="""
def evaluate_rule(data):
    return data['risk_level'] == 'Low'
"""
        ),
        # Case 5: Python Syntax Error (Missing Colon)
        TestCase(
            id="RULE-005",
            description="Syntax Error: Malformed code syntax generated by LLM",
            category=ErrorCategory.SYNTAX_ERROR,
            input_data={"credit_score": 750, "monthly_income": 5000, "has_defaults": False, "customer_tier": "Gold"},
            expected_output=True,
            mock_llm_stlc_ast={
                "type": "BinaryOp", "op": "AND",
                "left": "INVALID_SYNTAX_NODE",  # Invalid AST structure
                "right": {"type": "Literal", "value": True, "value_type": "Bool"}
            },
            mock_llm_python_code="""
def evaluate_rule(data)
    return data['credit_score'] > 700
"""
        )
    ]

# ==========================================
# 7. EXPERIMENT SUITE RUNNER & METRICS DISPLAY
# ==========================================

def run_v5_experiment():
    corpus = get_v5_benchmark_corpus()
    pipeline = ExperimentPipelineV5()

    print("===================================================================================")
    print(" EXPERIMENTAL COMPUTATIONAL MODEL PIPELINE - v5 (DI_PF_TFI_ENTREGA1_v5.pdf)")
    print("===================================================================================\n")

    res_treatment: List[ExecutionResult] = []
    res_b1: List[ExecutionResult] = []
    res_b2: List[ExecutionResult] = []

    for test in corpus:
        r_t = pipeline.run_treatment(test)
        r_b1 = pipeline.run_baseline_1(test)
        r_b2 = pipeline.run_baseline_2(test)

        res_treatment.append(r_t)
        res_b1.append(r_b1)
        res_b2.append(r_b2)

        print(f"--- Test Case [{test.id}]: {test.description} ({test.category.value}) ---")
        print(f"  [1. Treatment (STLC Haskell)] : Intercepted={r_t.intercepted_by_verifier} | Passed={r_t.passed_test} | Detail: {r_t.error_detected}")
        print(f"  [2. Baseline 1 (Python Free) ] : Intercepted={r_b1.intercepted_by_verifier} | Passed={r_b1.passed_test} | Detail: {r_b1.error_detected}")
        print(f"  [3. Baseline 2 (Python Struct)]: Intercepted={r_b2.intercepted_by_verifier} | Passed={r_b2.passed_test} | Detail: {r_b2.error_detected}\n")

    # Aggregate Metrics Computation
    total = len(corpus)

    def calc_stats(results: List[ExecutionResult]):
        pass1 = (sum(1 for r in results if r.passed_test) / total) * 100
        intercepted = sum(1 for r in results if r.intercepted_by_verifier)
        runtime_failures = sum(1 for r in results if r.runtime_failed)
        return pass1, intercepted, runtime_failures

    pass1_t, inc_t, rf_t = calc_stats(res_treatment)
    pass1_b1, inc_b1, rf_b1 = calc_stats(res_b1)
    pass1_b2, inc_b2, rf_b2 = calc_stats(res_b2)

    print("===================================================================================")
    print(" THREE-GROUP EXPERIMENTAL COMPARISON METRICS (DI_PF_TFI_ENTREGA1_v5)")
    print("===================================================================================")
    print(f"Total Test Scenarios Evaluated: {total}")
    print(f"1. Treatment Group (Functional STLC DSL in Haskell) : Pass@1 = {pass1_t:.1f}% | Intercepted = {inc_t}/{total} | Runtime Failures = {rf_t}/{total}")
    print(f"2. Baseline 1 (Control Libre en Python)             : Pass@1 = {pass1_b1:.1f}% | Intercepted = {inc_b1}/{total} | Runtime Failures = {rf_b1}/{total}")
    print(f"3. Baseline 2 (Control Estructurado en Python)       : Pass@1 = {pass1_b2:.1f}% | Intercepted = {inc_b2}/{total} | Runtime Failures = {rf_b2}/{total}")
    print("-----------------------------------------------------------------------------------")
    print("ERROR MIGRATION ANALYSIS:")
    print(f" - Treatment (STLC Haskell) avoided 100% of runtime errors by migrating {inc_t} errors to static typechecking.")
    print(f" - Baseline 2 (Python Struct) intercepted {inc_b2} errors statically, but let {rf_b2} errors leak to runtime/logic failure.")
    print(f" - Baseline 1 (Python Free) intercepted 0 errors statically; {rf_b1} errors hit runtime execution directly.")
    print("===================================================================================")

if __name__ == "__main__":
    run_v5_experiment()
