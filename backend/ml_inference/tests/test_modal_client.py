from types import SimpleNamespace

import numpy as np
import pytest

from backend.ml_inference import InferenceConfig
from backend.ml_inference.modal_client import ModalFeatureExtractor, ModalInterestScorer
from backend.ml_inference.transport import decode_window


class Handle:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
        self.cancelled = []

    def get(self, timeout):
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.result

    def cancel(self, **kwargs):
        self.cancelled.append(kwargs)


class Method:
    def __init__(self, function):
        self.function = function

    def spawn(self, *args):
        return self.function(*args)


def sdk_fixture(feature=None, ready=None, predict=None):
    lookups, options, parameters = [], [], []
    feature = feature or (lambda payload: Handle(np.zeros((75, 215), np.float32)))
    ready = ready or (lambda: Handle({"schema": "matchpulse-215-v1", "input_shape": [75, 215], "audio_required": True, "model_input_size": 215}))
    predict = predict or (lambda f: Handle({key: 0.5 for key in f}))

    class Worker:
        def __init__(self, name):
            self.name = name

        def with_options(self, **kwargs):
            options.append(kwargs)
            return self

        def __call__(self, **kwargs):
            parameters.append(kwargs)
            return SimpleNamespace(extract=Method(feature), ready=Method(ready), predict=Method(predict))

    class Cls:
        @staticmethod
        def from_name(app, name):
            assert app == "matchpulse-inference"
            lookups.append((app, name))
            return Worker(name)

    sdk = SimpleNamespace(Cls=Cls, exception=SimpleNamespace(TimeoutError=TimeoutError,
                                                           FunctionTimeoutError=TimeoutError))
    return sdk, lookups, options, parameters


def test_modal_dispatch_lossless_preserves_pixels_and_config():
    frames = np.random.default_rng(4).integers(0, 256, (75, 16, 24, 3), dtype=np.uint8)
    received = []

    def extract(payload):
        received.append(decode_window(payload))
        return Handle(np.zeros((75, 215), np.float32))

    sdk, lookups, options, parameters = sdk_fixture(feature=extract)
    client = ModalFeatureExtractor(InferenceConfig(mode="features_mock", gpu="T4"), sdk=sdk)
    assert not lookups
    assert client.extract("a", frames).shape == (75, 215)
    client.extract("b", frames)
    np.testing.assert_array_equal(received[0], frames)
    assert len(lookups) == 1 and options[0]["gpu"] == "T4"
    assert options[0]["max_containers"] == 1 and parameters[0]["fp16"] is True


def test_timeout_cancels_input_without_stopping_app():
    handle = Handle(error=TimeoutError())
    sdk, *_ = sdk_fixture(feature=lambda payload: handle)
    client = ModalFeatureExtractor(InferenceConfig(mode="features_mock"), sdk=sdk)
    with pytest.raises(TimeoutError, match="exceeded"):
        client.extract("a", np.zeros((75, 16, 16, 3), np.uint8))
    assert handle.cancelled == [{"terminate_containers": False}]


def test_cancelled_request_never_submits_more_inputs():
    sdk, lookups, *_ = sdk_fixture()
    client = ModalFeatureExtractor(InferenceConfig(mode="features_mock"), sdk=sdk)
    client.cancel_pending()
    with pytest.raises(TimeoutError, match="cancelled"):
        client.extract("a", np.zeros((75, 16, 16, 3), np.uint8))
    assert not lookups


def test_real_modal_cpu_batch_and_readiness_once():
    sdk, lookups, options, parameters = sdk_fixture()
    scorer = ModalInterestScorer(InferenceConfig(mode="real", checkpoint="v1/classifier.pt"), sdk=sdk)
    x = np.zeros((75, 215), np.float32)
    x[:, 214] = 1
    assert scorer.predict_scores({"a": x, "b": x}) == {"a": 0.5, "b": 0.5}
    scorer.predict_scores({"a": x})
    assert lookups == [("matchpulse-inference", "ClassifierWorker")]
    assert "gpu" not in options[0]
    assert parameters == [{"checkpoint_name": "v1/classifier.pt"}]


def test_missing_remote_checkpoint_raises_instead_of_mocking():
    sdk, *_ = sdk_fixture(ready=lambda: Handle(error=FileNotFoundError("missing classifier.pt")))
    scorer = ModalInterestScorer(InferenceConfig(mode="real", checkpoint="classifier.pt"), sdk=sdk)
    with pytest.raises(FileNotFoundError):
        scorer.prepare()


def test_wrong_deployed_schema_rejected():
    sdk, *_ = sdk_fixture(ready=lambda: Handle({"schema": "other", "input_shape": [75, 215]}))
    scorer = ModalInterestScorer(InferenceConfig(mode="real", checkpoint="classifier.pt"), sdk=sdk)
    with pytest.raises(ValueError, match="schema"):
        scorer.prepare()
