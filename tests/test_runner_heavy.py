from backend.workers import runner


def test_heavy_jobs_registered():
    for name in ("analyze", "scene_classify", "gaming_classify"):
        assert name in runner.HEAVY


def test_runner_api_exists():
    assert hasattr(runner, "register")
    assert hasattr(runner, "JobContext")
    assert hasattr(runner, "JobCancelled")