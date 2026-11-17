from app.services import llm


class _Resp:
    text = '{"skills": ["Python"]}'


class _FakeModels:
    def __init__(self, fail_models):
        self.fail, self.calls = fail_models, []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if model in self.fail:
            raise RuntimeError("429 quota exceeded")
        return _Resp()


class _FakeClient:
    def __init__(self, fail_models=()):
        self.models = _FakeModels(fail_models)


def _setup(monkeypatch, fail=()):
    fake = _FakeClient(fail)
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    llm._cache.clear()
    return fake.models


def test_fast_tier_uses_lite_model(monkeypatch):
    calls = _setup(monkeypatch).calls
    assert llm.generate_text("hi", tier="fast") is not None
    assert calls == [llm.MODELS["fast"]]


def test_fallback_when_quota_exceeded(monkeypatch):
    models = _setup(monkeypatch, fail=(llm.MODELS["smart"],))
    assert llm.generate_text("grade this", tier="smart") is not None
    assert models.calls == [llm.MODELS["smart"], llm.MODELS["fast"]]


def test_cache_avoids_second_call(monkeypatch):
    models = _setup(monkeypatch)
    llm.generate_text("same prompt")
    llm.generate_text("same prompt")
    assert len(models.calls) == 1


def test_both_fail_returns_none(monkeypatch):
    _setup(monkeypatch, fail=tuple(llm.MODELS.values()))
    assert llm.generate_text("x") is None


def test_a_stalled_request_is_sent_again_and_the_first_answer_wins(monkeypatch):
    """Live interview: Gemini sometimes stalls on one request; a second one usually answers fast."""
    import threading
    import time

    from pydantic import BaseModel

    class Skills(BaseModel):
        skills: list[str]

    release, calls = threading.Event(), []

    def generate(model, prompt, config):
        calls.append(time.monotonic())
        if len(calls) == 1:
            release.wait(5)                  # the first request stalls
        return '{"skills": ["Python"]}'
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_generate", generate)
    llm._cache.clear()
    t = time.monotonic()
    out = llm.generate_json("stall", Skills, timeout=3, quick=True, hedge_after=0.3)
    release.set()
    assert out == {"skills": ["Python"]} and len(calls) == 2
    assert time.monotonic() - t < 1.5        # not the stalled request's time
    # a fast answer is never sent twice
    llm._cache.clear()
    calls.clear()
    llm.generate_json("fast", Skills, timeout=3, hedge_after=0.3)
    assert len(calls) == 1
