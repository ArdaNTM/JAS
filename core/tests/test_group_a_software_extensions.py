"""Group A functional extensions: real Core/Gateway, SQLite, report and science E2E.

No fake safety verdict, no network/hardware or production Owner identity.
Fixtures exercise real providers/registries and negative security boundaries.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import zipfile
import time

import pytest

from aura_core.application.task_state_machine import TaskStateMachine
from aura_core.application.task_priority import (
    TaskPriorityLedger, GovernedTaskPriorityMCP, register_governed_task_priority,
    TASK_PRIORITY_CAPS,
)
from aura_core.application.workspace_architecture import (
    inspect_source_workspace, GovernedArchitectureMCP, register_governed_architecture,
)
from aura_core.config.backend import BackendConfig
from aura_core.config.kernel import KernelConfig
from aura_core.config.logging import LoggingConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.data_analysis.governed_csv import (
    GovernedCSVAnalysisMCP, register_governed_csv_analysis, scan_csv_numeric_stream,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionPolicy, RiskLevel,
)
from aura_core.kernel.runtime import AuraKernel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.research.archive import SQLiteResearchArchive
from aura_core.research.citations import CitationReview
from aura_core.research.report_authoring import ReportSection, author_research_report
from aura_core.science.model_uncertainty import fit_ols_with_uncertainty
from aura_core.science.experiment_dataset import analyze_experiment_csv, render_experiment_markdown


def setup_kernel():
    kernel = AuraKernel(KernelConfig(
        runtime=RuntimeConfig(runtime="mock", model="test-local-model"),
        backend=BackendConfig(), logging=LoggingConfig(),
    ))
    kernel.bootstrap()
    kernel.start()
    return kernel


def invoke(gw, cap, tool, principal, scope, **args):
    return asyncio.run(gw.invoke(MCPGatewayRequest(
        request_id=principal+"-"+tool, principal_id=principal,
        capability_id=cap, operation_id=cap, resource_scope=scope,
        risk_level=RiskLevel.LOW, tool_name=tool, arguments=args,
    )))


def allow(kernel, principal, cap, scope):
    kernel.permission_engine.add_policy(PermissionPolicy(
        policy_id=principal+"."+cap, policy_version="1",
        principal_id=principal, capability_id=cap, operation_id=cap,
        resource_scope=scope, authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))


def test_durable_task_priority_gateway_and_scope_denial(tmp_path):
    kernel = setup_kernel()
    store = TaskStateMachine(tmp_path / "tasks.sqlite")
    task = store.create_task(principal_id="alice", goal="Prepare release")
    ledger = TaskPriorityLedger(store, tmp_path / "priorities.sqlite")
    provider = GovernedTaskPriorityMCP(ledger)
    register_governed_task_priority(kernel, provider)
    gw = MCPGateway(kernel.capability_registry, kernel.provider_registry,
                    kernel.permission_engine, event_bus=kernel.event_bus)
    cap = TASK_PRIORITY_CAPS["task_priority_set"]
    denied = invoke(gw, cap, "task_priority_set", "alice", "tasks/alice",
                    task_id=task.task_id, priority=5, expected_revision=0)
    assert denied.decision is AuthorizationDecision.DENY
    allow(kernel, "alice", cap, "tasks/alice")
    good = invoke(gw, cap, "task_priority_set", "alice", "tasks/alice",
                  task_id=task.task_id, priority=5, expected_revision=0)
    assert good.decision is AuthorizationDecision.ALLOW
    assert good.result["revision"] == 1
    with pytest.raises(ValueError, match="revision conflict"):
        invoke(gw, cap, "task_priority_set", "alice", "tasks/alice",
               task_id=task.task_id, priority=2, expected_revision=0)
    outside = invoke(gw, cap, "task_priority_set", "bob", "tasks/bob",
                     task_id=task.task_id, priority=1, expected_revision=1)
    assert outside.decision is AuthorizationDecision.DENY
    ledger.close()
    reloaded = TaskPriorityLedger(store, tmp_path / "priorities.sqlite")
    assert reloaded.get(principal_id="alice", task_id=task.task_id)["priority"] == 5
    with pytest.raises((KeyError, ValueError)):
        reloaded.get(principal_id="bob", task_id=task.task_id)
    reloaded.close()
    store.close()
    kernel.stop()


def test_read_only_multifile_architecture_gateway_exact_scope():
    kernel = setup_kernel()
    source = {
        "a.py": "import b\n\ndef example():\n    return 1\n",
        "b.py": "class Storage:\n    pass\n",
        "C.java": "import java.util.List; public class C {}",
    }
    module = GovernedArchitectureMCP({"alice": source})
    register_governed_architecture(kernel, module)
    gw = MCPGateway(kernel.capability_registry, kernel.provider_registry,
                    kernel.permission_engine)
    cap = "aura.coding.architecture.inspect"
    assert invoke(gw, cap, "architecture_inspect", "alice", "repos/alice").decision is AuthorizationDecision.DENY
    allow(kernel, "alice", cap, "repos/alice")
    accepted = invoke(gw, cap, "architecture_inspect", "alice", "repos/alice")
    assert accepted.decision is AuthorizationDecision.ALLOW
    assert {"source":"a.py","dependency":"b.py"} in accepted.result["edges"]
    assert accepted.result["security_verified"] is False
    assert accepted.result["code_executed"] is False
    forged = invoke(gw, cap, "architecture_inspect", "alice", "repos/alice",
                    path="../../secret")
    assert forged.decision is AuthorizationDecision.DENY
    kernel.stop()


@pytest.mark.parametrize("path", ["../escape.py", "/tmp/a.py", "a.exe", "x\x00.py"])
def test_multifile_invalid_source_paths_are_rejected(path):
    with pytest.raises(ValueError):
        inspect_source_workspace({path: "print('x')"})


def test_docx_report_real_zip_no_external_relations_or_executed_formulas():
    review = CitationReview(
        doi="10.1234/research", title="Neutral Study",
        authors=("A. Researcher",), publication_year=2025,
        venue="Journal", source_ids=("publisher",),
        conflicting_metadata=False,
    )
    report = author_research_report(
        title="Bounded research",
        sections=(ReportSection(
            heading="Results", body="The expression =1+1 is untrusted data.",
            cited_dois=("10.1234/research",)),),
        citations=(review,),
    )
    assert "DOI:" in report.markdown()
    assert report.source_authenticity_verified is False
    data = report.docx()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.namelist() == [
            "[Content_Types].xml", "_rels/.rels", "word/document.xml",
        ]
        xml = z.read("word/document.xml")
        assert b"=1+1" in xml and b"Neutral Study" in xml
        assert b"hyperlink" not in xml
    with pytest.raises(ValueError, match="unreviewed DOI"):
        author_research_report(
            title="Broken",
            sections=(ReportSection("Results", "Detail", ("10.9999/missing",)),),
            citations=(review,),
        )
    conflict = CitationReview(
        doi=review.doi, title=review.title, authors=review.authors,
        publication_year=2025, venue=review.venue,
        source_ids=review.source_ids, conflicting_metadata=True,
    )
    with pytest.raises(ValueError, match="conflicting"):
        author_research_report(
            title="Wrong", sections=(ReportSection("S", "B", (review.doi,)),),
            citations=(conflict,),
        )


def test_archive_scoped_browse_retention_and_integrity(tmp_path):
    """No invented provider authenticity: a persisted response is untrusted."""
    from aura_core.mcp.gateway import MCPGatewayResponse
    archive = SQLiteResearchArchive(tmp_path / "archive.sqlite")
    approved_response = MCPGatewayResponse(
        decision=AuthorizationDecision.ALLOW,
        result={
            "url": "https://example.org/paper",
            "status_code": 200, "content_type": "text/html",
            "content": "<article>Offline snapshot</article>",
        },
        provider_id="source", tool_name="fetch", reason="test-only fixture",
    )
    saved = archive.archive_fetch_result(
        principal_id="alice", response=approved_response, consented=True)
    assert saved["verified_source"] is False
    summaries = archive.list_snapshots(principal_id="alice")
    assert len(summaries) == 1
    assert "content" not in summaries[0]
    assert archive.list_snapshots(principal_id="bob") == ()
    with pytest.raises(PermissionError):
        archive.prune_before(principal_id="alice", cutoff_timestamp=999999999999.0)
    with pytest.raises(ValueError):
        archive.prune_before(principal_id="alice", cutoff_timestamp=999999999999.0,
                             confirmed=True)
    assert archive.get(principal_id="alice", archive_id=saved["archive_id"])
    assert archive.prune_before(principal_id="bob", cutoff_timestamp=999999999.0,
                                confirmed=True) == 0
    assert archive.prune_before(principal_id="alice", cutoff_timestamp=time.time(),
                                confirmed=True) == 1
    assert archive.list_snapshots(principal_id="alice") == ()


def test_ols_parameter_errors_and_large_sample_asymptotic_interval():
    xs = list(range(50))
    ys = [2 * x + 5 + (x % 3) * 0.1 for x in xs]
    a = fit_ols_with_uncertainty(xs, ys)
    b = fit_ols_with_uncertainty(tuple(xs), tuple(ys))
    assert a.to_dict() == b.to_dict()
    assert a.degrees_freedom == 48
    assert a.slope_standard_error >= 0
    assert a.slope_interval_95_approx[0] < a.slope < a.slope_interval_95_approx[1]
    assert a.assumptions_verified is False
    with pytest.raises(ValueError):
        fit_ols_with_uncertainty([1,1,1], [1,2,3])
    with pytest.raises(ValueError):
        fit_ols_with_uncertainty([1,2], [3,4])


def test_real_csv_experiment_provenance_comparison_and_no_false_significance():
    raw = "group,val\nA,2\nA,4\nB,6\nB,8\n"
    report = analyze_experiment_csv(
        raw, study_id="exp-42", measure_column="val", group_column="group")
    assert report.sample_count == 4
    assert report.data_sha256 == hashlib.sha256(raw.encode()).hexdigest()
    assert report.result["comparison"]["mean_difference"] == 4
    assert report.source_authenticated is False
    assert "NOT independently validated" in render_experiment_markdown(report)
    assert analyze_experiment_csv(
        raw, study_id="exp-42", measure_column="val", group_column="group"
    ).report_sha256 == report.report_sha256
    with pytest.raises(ValueError):
        analyze_experiment_csv(
            raw.replace("B,8", "B,nan"), study_id="exp-42",
            measure_column="val", group_column="group")


def test_csv_gateway_real_xlsx_literal_export_and_streaming():
    kernel = setup_kernel()
    provider = GovernedCSVAnalysisMCP()
    register_governed_csv_analysis(kernel, provider)
    gw = MCPGateway(kernel.capability_registry, kernel.provider_registry,
                    kernel.permission_engine)
    csv_text = "name,value\n=2+2,4\nnormal,8\n"
    cap = "aura.data.csv.export"
    assert invoke(gw, cap, "csv_export_xlsx", "alice", "data/alice",
                  csv_text=csv_text).decision is AuthorizationDecision.DENY
    allow(kernel, "alice", cap, "data/alice")
    accepted = invoke(gw, cap, "csv_export_xlsx", "alice", "data/alice",
                      csv_text=csv_text)
    assert accepted.decision is AuthorizationDecision.ALLOW
    data = base64.b64decode(accepted.result["base64"])
    assert hashlib.sha256(data).hexdigest() == accepted.result["sha256"]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("xl/worksheets/sheet1.xml")
        assert b't="inlineStr"' in xml and b"=2+2" in xml
    denied = invoke(gw, cap, "csv_export_xlsx", "alice", "data/alice",
                    csv_text=csv_text, filename="../../secrets")
    assert denied.decision is AuthorizationDecision.DENY
    src = ("value\n" if x == -1 else f"{x}\n" for x in range(-1, 4000))
    summary = scan_csv_numeric_stream(src, numeric_column="value")
    assert summary["count"] == 4000
    assert abs(summary["mean"] - 1999.5) < 1e-8
    assert summary["source_authenticated"] is False
    kernel.stop()
