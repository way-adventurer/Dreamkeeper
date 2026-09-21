import sys

from runrelay.models import Experiment, Status
from runrelay.wake import CommandWake


def test_command_wake_exports_completion_context(tmp_path):
    experiment = Experiment(
        id="exp_wake",
        host="gpu-test",
        workdir="/workspace/project",
        command="python train.py",
        status=Status.COMPLETED,
        exit_code=0,
        local_dir=str(tmp_path),
        wake_command=(
            f'"{sys.executable}" -c "import os; print(os.environ[\'RUNRELAY_EXPERIMENT_ID\'] + \':\' + os.environ[\'RUNRELAY_STATUS\'] + \':\' + os.environ[\'RUNRELAY_EXIT_CODE\'])"'
        ),
    )

    result = CommandWake().wake(experiment)

    assert result == "exp_wake:COMPLETED:0"
