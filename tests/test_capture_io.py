import os

from capture_io import (
    copy_screenshot,
    resolve_unique_path,
    sanitize_filename,
    write_spectrum_csv,
)


class TestSanitizeFilename:
    def test_normal_name_preserved(self):
        assert sanitize_filename("捕获_20251010_143025_TRA") == "捕获_20251010_143025_TRA"

    def test_illegal_chars_replaced(self):
        assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"

    def test_strips_surrounding_whitespace(self):
        assert sanitize_filename("  name  ") == "name"

    def test_empty_returns_fallback(self):
        assert sanitize_filename("") == "capture"

    def test_whitespace_only_returns_fallback(self):
        assert sanitize_filename("   ") == "capture"

    def test_control_chars_replaced(self):
        assert sanitize_filename("a\nb\tc") == "a_b_c"


class TestResolveUniquePath:
    def test_no_conflict_returns_plain_name(self, tmp_path):
        used: set[str] = set()
        path = resolve_unique_path(str(tmp_path), "cap", ".csv", used)
        assert os.path.basename(path) == "cap.csv"

    def test_registers_result_in_used(self, tmp_path):
        used: set[str] = set()
        path = resolve_unique_path(str(tmp_path), "cap", ".csv", used)
        assert path in used

    def test_used_conflict_appends_suffix(self, tmp_path):
        used: set[str] = set()
        first = resolve_unique_path(str(tmp_path), "cap", ".csv", used)
        second = resolve_unique_path(str(tmp_path), "cap", ".csv", used)
        assert os.path.basename(first) == "cap.csv"
        assert os.path.basename(second) == "cap_1.csv"

    def test_disk_conflict_appends_suffix(self, tmp_path):
        (tmp_path / "cap.csv").write_text("existing")
        used: set[str] = set()
        path = resolve_unique_path(str(tmp_path), "cap", ".csv", used)
        assert os.path.basename(path) == "cap_1.csv"

    def test_consecutive_conflicts_increment(self, tmp_path):
        used: set[str] = set()
        names = [
            os.path.basename(resolve_unique_path(str(tmp_path), "cap", ".csv", used))
            for _ in range(3)
        ]
        assert names == ["cap.csv", "cap_1.csv", "cap_2.csv"]


class TestWriteSpectrumCsv:
    def test_writes_rows_no_header(self, tmp_path):
        path = str(tmp_path / "out.csv")
        write_spectrum_csv([1.0, 2.0], [-10.5, -20.5], path)
        content = (tmp_path / "out.csv").read_text()
        assert content == "1.0,-10.5\n2.0,-20.5\n"

    def test_line_count_matches_points(self, tmp_path):
        path = str(tmp_path / "out.csv")
        write_spectrum_csv([1, 2, 3], [4, 5, 6], path)
        lines = (tmp_path / "out.csv").read_text().splitlines()
        assert len(lines) == 3


class TestCopyScreenshot:
    def test_copies_bytes_exactly(self, tmp_path):
        src = tmp_path / "src.bmp"
        src.write_bytes(b"\x00\x01\x02BMPDATA")
        dst = str(tmp_path / "dst.bmp")
        copy_screenshot(str(src), dst)
        assert (tmp_path / "dst.bmp").read_bytes() == b"\x00\x01\x02BMPDATA"
