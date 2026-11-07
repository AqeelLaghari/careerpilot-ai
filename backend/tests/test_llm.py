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
