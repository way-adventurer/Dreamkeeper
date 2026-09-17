from runrelay.models import Experiment, Status
from runrelay.wake import CodexCliResumeWake


def test_codex_cli_wake_resumes_saved_thread(monkeypatch, tmp_path):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class Result:
            returncode = 0
            stdout = '{"type":"turn.completed"}\n'
            stderr = ""

        return Result()

    monkeypatch.setattr("runrelay.wake.subprocess.run", fake_run)
    experiment = Experiment(
        id="exp_wake",
        host="gpu-test",
        workdir="/workspace/project",
        command="python train.py",
        status=Status.COMPLETED,
        exit_code=0,
        local_dir=str(tmp_path),
        git_repo=str(tmp_path),
        session_id="thread-123",
    )

    result = CodexCliResumeWake().wake(experiment)

    assert result == "Codex CLI resume completed."
    assert captured["args"][:4] == ["codex", "exec", "resume", "thread-123"]
    assert "Dreamkeeper experiment exp_wake finished" in captured["args"][4]
    assert (tmp_path / "codex-wake.jsonl").read_text(encoding="utf-8").strip()
