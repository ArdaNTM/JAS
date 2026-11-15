"""Features #46/#50: AST-only bug indicators and real runnable contract tests."""
from __future__ import annotations

import ast
import hashlib
import pytest

from aura_core.application.offline_code_quality import (
    ContractCase, generate_pytest_contracts, review_static_python,
)


def test_static_review_detects_real_patterns_without_executing_source(tmp_path):
    destination = tmp_path / "should-not-exist"
    source = f"""
open({str(destination)!r}, 'w').write('bad')
def f(x=[]):
    return x
    print('unreachable')
try:
    x = eval('1 + 2')
except:
    pass
"""
    result = review_static_python(source)
    assert not destination.exists()
    assert [finding.category for finding in result.findings] == [
        "mutable_default", "unreachable_after_exit",
        "dynamic_code_call", "bare_except",
    ]
    assert all(finding.untrusted and not finding.bug_confirmed
               for finding in result.findings)
    assert not result.code_executed and not result.bug_confirmed
    assert not result.authorization_checked


def test_safe_python_source_returns_no_findings():
    result = review_static_python(
        "def double(value: int) -> int:\n    return value * 2\n"
    )
    assert result.findings == ()
    assert len(result.source_sha256) == 64


def test_generated_pytest_cases_execute_against_controlled_stdlib_module():
    suite = generate_pytest_contracts(
        module_name="operator", cases=(
            ContractCase("add", (2, 3), {}, 5),
            ContractCase("mul", (4, 5), {}, 20),
        ),
    )
    assert suite.case_count == 2
    assert not suite.executed and not suite.tests_passed
    assert not suite.sandbox_authorization_checked
    assert hashlib.sha256(suite.code.encode()).hexdigest() == suite.source_sha256
    ast.parse(suite.code)
    # Only this CI test intentionally executes the generated reviewed output,
    # against known harmless standard-library arithmetic functions.
    scope = {}
    exec(compile(suite.code, "<generated-contract-test>", "exec"), scope)
    scope["test_generated_contract"]("add", "[2, 3]", "{}", "5")
    scope["test_generated_contract"]("mul", "[4, 5]", "{}", "20")


def test_untrusted_data_is_literal_not_python_code():
    injected = "'; __import__('os').system('echo never'); #"
    suite = generate_pytest_contracts(
        module_name="operator",
        cases=(ContractCase("add", (injected, "test"), {}, injected + "test"),),
    )
    ast.parse(suite.code)
    assert "importlib.import_module('operator')" in suite.code
    scope = {}
    exec(compile(suite.code, "<safe-test>", "exec"), scope)
    scope["test_generated_contract"](
        "add", '["\\u0027; __import__(\\u0027os\\u0027).system(\\u0027echo never\\u0027); #", "test"]',
        "{}", '"\\u0027; __import__(\\u0027os\\u0027).system(\\u0027echo never\\u0027); #test"',
    )


@pytest.mark.parametrize("invalid", [
    "", "def invalid(", "\x00", "x = '\ud800'", "x" * 131073,
])
def test_invalid_or_oversized_source_rejected(invalid):
    with pytest.raises(ValueError):
        review_static_python(invalid)


@pytest.mark.parametrize("name", [
    "../unsafe", "os;eval('x')", "__private", "os.__loader__", "",
])
def test_unsafe_destination_module_rejected(name):
    with pytest.raises(ValueError):
        generate_pytest_contracts(
            module_name=name, cases=(ContractCase("add", (1, 2), {}, 3),),
        )


@pytest.mark.parametrize("cases", [
    (),
    [ContractCase("add", (1, 2), {}, 3)],
    (ContractCase("__import__", (1,), {}, 1),),
    (ContractCase("bad;os.system", (), {}, 1),),
    (ContractCase("add", (float("nan"), 1), {}, 1),),
    (ContractCase("add", (object(),), {}, 1),),
    (ContractCase("add", (1, 2), {"../bad": "x"}, 3),),
    (ContractCase("add", tuple(range(17)), {}, 3),),
])
def test_invalid_or_untrusted_test_contracts_rejected(cases):
    with pytest.raises(ValueError):
        generate_pytest_contracts(module_name="operator", cases=cases)


def test_generated_source_reproducible_and_never_autorun():
    cases = (ContractCase("add", (1, 5), {}, 6),)
    assert generate_pytest_contracts(
        module_name="operator", cases=cases,
    ) == generate_pytest_contracts(module_name="operator", cases=cases)
