import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from contestflow import core, project, reporting, runner


def posix_context(child=True, leader=True):
    return SimpleNamespace(
        name="posix",
        environ={"CONTESTFLOW_PREFLIGHT_CHILD": "1"} if child else {},
        getpid=lambda: 100,
        getsid=lambda pid: 100 if leader else 50,
        getpgrp=lambda: 100 if leader else 50,
    )


def test_preflight_descendants_share_the_outer_session(monkeypatch):
    monkeypatch.setattr(runner, "os", posix_context())
    assert runner.child_process_options() == {}
    monkeypatch.setattr(runner, "os", posix_context(child=False))
    assert runner.child_process_options() == {"start_new_session": True}


def test_preflight_mode_refuses_a_shared_host_session(monkeypatch):
    context = posix_context(leader=False)
    context.killpg = lambda *args: pytest.fail("must not kill a shared host group")
    monkeypatch.setattr(runner, "os", context)
    with pytest.raises(core.FlowError, match="isolated"):
        runner.child_process_options()
    with pytest.raises(core.FlowError, match="host process group"):
        runner.kill_tree(SimpleNamespace(pid=101))


def test_internal_timeout_aborts_only_its_isolated_probe_group(monkeypatch):
    context = posix_context()
    killed = []
    context.killpg = lambda group, sig: killed.append((group, sig))
    monkeypatch.setattr(runner, "signal", SimpleNamespace(SIGKILL=9))
    monkeypatch.setattr(runner, "os", context)
    with pytest.raises(core.FlowError, match="terminated"):
        runner.kill_tree(SimpleNamespace(pid=101))
    assert killed == [(100, 9)]


@pytest.mark.parametrize(
    "system,font",
    [
        ("Windows", "Microsoft YaHei"),
        ("Darwin", "PingFang SC"),
        ("Linux", "Noto Sans CJK SC"),
    ],
)
def test_chinese_font_default_is_shared_and_does_not_mutate_preferences(monkeypatch, system, font):
    monkeypatch.setattr(reporting.platform, "system", lambda: system)
    settings = {"cjk_font": "", "main_font": "Custom Serif", "fontsize": "11pt"}
    effective = reporting.paper_font_settings(settings, "中文测试")
    assert effective["cjk_font"] == font
    assert effective["main_font"] == settings["main_font"]
    assert settings["cjk_font"] == ""
    assert reporting.paper_font_settings(settings, "English text") == settings
    assert (
        reporting.paper_font_settings({"cjk_font": "Custom CJK"}, "中文")["cjk_font"]
        == "Custom CJK"
    )


def test_production_engine_options_do_not_run_version_commands(monkeypatch):
    monkeypatch.delenv("CONTESTFLOW_PREFLIGHT_CHILD", raising=False)
    monkeypatch.setattr(
        reporting.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected probe")
    )
    assert reporting.preflight_pdf_engine_options("xelatex") == []


@pytest.mark.parametrize(
    "version,expected",
    [
        ("MiKTeX-XeTeX 4.19 (MiKTeX 26.4)", ["--pdf-engine-opt=-disable-installer"]),
        ("XeTeX 3.141 (TeX Live 2026)", []),
    ],
)
def test_preflight_engine_options_disable_miktex_installer(monkeypatch, version, expected):
    monkeypatch.setenv("CONTESTFLOW_PREFLIGHT_CHILD", "1")
    monkeypatch.setattr(reporting, "child_process_options", lambda: {})
    invocations = []

    def communicate(timeout):
        assert timeout == 10
        return version, ""

    process = SimpleNamespace(communicate=communicate, returncode=0)
    monkeypatch.setattr(
        reporting.subprocess, "Popen", lambda argv, **kwargs: invocations.append(argv) or process
    )
    assert reporting.preflight_pdf_engine_options("selected xelatex") == expected
    assert invocations == [["selected xelatex", "--version"]]


def test_unknown_or_hanging_tex_fails_before_compilation(monkeypatch):
    monkeypatch.setenv("CONTESTFLOW_PREFLIGHT_CHILD", "1")
    monkeypatch.setattr(reporting, "child_process_options", lambda: {})
    process = SimpleNamespace(communicate=lambda timeout: ("unknown wrapper", ""), returncode=0)
    monkeypatch.setattr(reporting.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(core.FlowError, match="identify"):
        reporting.preflight_pdf_engine_options("xelatex")

    def timeout(timeout):
        raise subprocess.TimeoutExpired("xelatex", timeout)

    process.communicate = timeout
    killed = []
    monkeypatch.setattr(reporting, "kill_tree", lambda proc: killed.append(proc))
    with pytest.raises(core.FlowError, match="timed out"):
        reporting.preflight_pdf_engine_options("xelatex")
    assert killed == [process]


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group integration")
def test_nested_timeout_does_not_leave_a_grandchild_running(tmp_path):
    # A late sentinel proves a surviving grandchild without relying on zombie/PID checks.
    sentinel = tmp_path / "escaped.txt"
    grandchild = (
        "import time; from pathlib import Path; time.sleep(2); Path("
        + repr(str(sentinel))
        + ").write_text('escaped')"
    )
    child = (
        "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
        + repr(grandchild)
        + "]); time.sleep(20)"
    )
    probe = (
        "import subprocess,sys,time; from contestflow.runner import child_process_options,kill_tree; "
        "p=subprocess.Popen([sys.executable,'-c'," + repr(child) + "],**child_process_options()); "
        "time.sleep(0.5); kill_tree(p)"
    )
    env = os.environ.copy()
    env["CONTESTFLOW_PREFLIGHT_CHILD"] = "1"
    env["PYTHONPATH"] = str(Path(runner.__file__).resolve().parent.parent)
    process = subprocess.Popen([sys.executable, "-c", probe], env=env, start_new_session=True)
    try:
        assert process.wait(timeout=5) == -signal.SIGKILL
        time.sleep(2.2)
        assert not sentinel.exists()
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


@pytest.mark.parametrize("text,chinese", [("中文正文", True), ("English manuscript", False)])
def test_pdf_build_uses_shared_font_and_preflight_engine_options(
    tmp_path, monkeypatch, text, chinese
):
    root = tmp_path / "workspace"
    project.init(root, "Test paper")
    context = {"selection": {"table_style": "plain"}}
    monkeypatch.setattr(reporting, "paper_context", lambda root: context)
    monkeypatch.setattr(reporting, "resolved_markdown", lambda root: text)
    monkeypatch.setattr(reporting, "pandoc_path", lambda root: "chosen-pandoc")
    monkeypatch.setattr(reporting, "resolve_tool", lambda name, root: "chosen-xelatex")
    monkeypatch.setattr(reporting.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        reporting,
        "preflight_pdf_engine_options",
        lambda engine: ["--pdf-engine-opt=-disable-installer"],
    )
    commands = []

    def popen(argv, **kwargs):
        commands.append(argv)
        target = Path(argv[argv.index("-o") + 1])
        target.write_bytes(b"%PDF test fixture")
        return SimpleNamespace(communicate=lambda timeout: ("", ""), returncode=0)

    monkeypatch.setattr(reporting.subprocess, "Popen", popen)
    reporting.build_paper(root, "pdf")
    assert len(commands) == 1
    assert ("CJKmainfont=Microsoft YaHei" in commands[0]) is chinese
    assert "--pdf-engine-opt=-disable-installer" in commands[0]
    assert "--pdf-engine=chosen-xelatex" in commands[0]
