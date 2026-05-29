import pytest

from osa import osa, SWEEP_FINISHED_BIT


class TestParseInt:
    def test_crlf(self):
        assert osa._parse_int(b"1\r\n") == 1

    def test_zero(self):
        assert osa._parse_int(b"0") == 0

    def test_none(self):
        assert osa._parse_int(None) == 0

    def test_garbage(self):
        assert osa._parse_int(b"abc") == 0

    def test_with_spaces(self):
        assert osa._parse_int(b"  3 \r\n") == 3


class TestPollSweepFinished:
    def _make(self, response):
        obj = osa.__new__(osa)  # 跳过 __init__，不连真机
        obj.query = lambda *a, **k: response
        return obj

    def test_finished_bit_set(self):
        assert self._make(b"1\r\n").poll_sweep_finished() is True

    def test_finished_bit_set_with_other_bits(self):
        # 值=3（二进制 11），bit0 置位
        assert self._make(b"3\r\n").poll_sweep_finished() is True

    def test_finished_bit_clear(self):
        assert self._make(b"0\r\n").poll_sweep_finished() is False

    def test_other_bit_only(self):
        # 值=2（二进制 10），bit0 未置位
        assert self._make(b"2\r\n").poll_sweep_finished() is False

    def test_none_response(self):
        assert self._make(None).poll_sweep_finished() is False


class TestScanCommands:
    def _make(self):
        obj = osa.__new__(osa)
        sent = []
        obj.send = lambda msg: sent.append(msg)
        return obj, sent

    def test_abort_sends_abort(self):
        obj, sent = self._make()
        obj.abort()
        assert sent == [":ABORt\n"]

    def test_start_sweep_sends_init(self):
        obj, sent = self._make()
        obj.start_sweep()
        assert sent == [":init\n"]


def test_sweep_finished_bit_value():
    assert SWEEP_FINISHED_BIT == 0b1
