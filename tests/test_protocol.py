import numpy as np
import pytest
from pydantic import ValidationError

from engine.fake_source import FakeSource
from engine.protocol import (
    N_BANDS,
    FeatureFrame,
    Prompt,
    ShaderCompiled,
    client_message_adapter,
)


def test_frame_roundtrip() -> None:
    f = FakeSource().frame(12.345)
    g = FeatureFrame.unpack(f.pack())
    np.testing.assert_array_equal(f.bands, g.bands)
    np.testing.assert_array_equal(f.waveform, g.waveform)
    np.testing.assert_array_equal(f.peaks, g.peaks)
    assert (g.bar, g.beat_in_bar) == (f.bar, f.beat_in_bar)
    assert g.kick == pytest.approx(f.kick)


def test_frame_size_is_small() -> None:
    # 64 + 512 + 24 float32 ≈ 2.4 KB; at 60 Hz ≈ 150 KB/s per client
    assert len(FakeSource().frame(1.0).pack()) < 3_000


def test_fake_source_ranges() -> None:
    src = FakeSource()
    for t in np.linspace(0, 120, 500):
        f = src.frame(float(t))
        for v in (f.kick, f.bass, f.mid, f.high, f.energy, f.beat_phase):
            assert 0.0 <= v <= 1.0
        assert f.bands.min() >= 0.0 and f.bands.max() <= 1.0
        assert np.abs(f.waveform).max() <= 1.0 + 1e-6
        assert 0 <= f.beat_in_bar <= 3


def test_bad_shape_rejected() -> None:
    f = FakeSource().frame(0.0)
    with pytest.raises(ValueError):
        FeatureFrame(**{**{s: getattr(f, s) for s in f.__slots__}, "bands": np.zeros(N_BANDS - 1)})


def test_client_messages() -> None:
    msg = client_message_adapter.validate_json('{"type":"prompt","text":"холодно, бетон"}')
    assert isinstance(msg, Prompt)
    msg = client_message_adapter.validate_json(
        '{"type":"shader.compiled","id":"x","ok":false,"error":"ERROR: 0:14"}'
    )
    assert isinstance(msg, ShaderCompiled) and not msg.ok
    with pytest.raises(ValidationError):
        client_message_adapter.validate_json('{"type":"prompt","text":""}')
    with pytest.raises(ValidationError):
        client_message_adapter.validate_json('{"type":"nope"}')
