from runrelay.models import Experiment, Status
from runrelay.storage import Storage


def test_storage_round_trip(tmp_path):
    storage = Storage(tmp_path)
    experiment = Experiment(
        id="exp_test",
        host="local",
        workdir=".",
        command="echo hi",
        created_at="now",
    )
    storage.put(experiment)
    loaded = storage.get("exp_test")
    assert loaded is not None
    assert loaded.status is Status.PENDING
    assert loaded.command == "echo hi"

