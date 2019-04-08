import datetime
import os
import pathlib
import tempfile
from typing import List, NamedTuple

import testtools

import hardlinkpy.hardlink as hardlink


class TestFileData(NamedTuple):
    pathname: str
    test_data: str
    mode: int
    timestamp: float


class TestFunctional(testtools.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.test_directory = pathlib.Path(self.temp_dir_obj.name)

        # Create five directories:
        # /tmp/.../dir0, ... /tmp/.../dir4
        for index in range(5):
            dirname = self.test_directory / f"dir{index}"
            os.mkdir(dirname)

        self.test_data_1 = "greeneggsandham" * 2048
        self.test_data_2 = "thecatandthehat" * 2048
        self.small_data_1 = "hellothere"

        timestamp_1 = datetime.datetime(2010, 1, 7, 11, 59, 23).timestamp()
        timestamp_2 = datetime.datetime(2019, 1, 7, 11, 59, 23).timestamp()

        self.test_file_data = [
            # dir0
            TestFileData(
                pathname="dir0/fileA_D1_T1.test",
                test_data=self.test_data_1,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            TestFileData(
                pathname="dir0/fileB_D2_T1.test",
                test_data=self.test_data_2,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            # dir1
            TestFileData(
                pathname="dir1/fileA_D2_T1.test",
                test_data=self.test_data_2,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            TestFileData(
                pathname="dir1/fileB_D1_T1.test",
                test_data=self.test_data_1,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            # dir2
            TestFileData(
                pathname="dir2/fileA_D1_T1.test",
                test_data=self.test_data_1,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            TestFileData(
                pathname="dir2/fileB_D1_T1.test",
                test_data=self.test_data_1,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            # dir3
            TestFileData(
                pathname="dir3/fileA_DS1_T1.test",
                test_data=self.small_data_1,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            TestFileData(
                pathname="dir3/fileB_D1_T1.test",
                test_data=self.test_data_1,
                mode=0o644,
                timestamp=timestamp_1,
            ),
            # dir4
            TestFileData(
                pathname="dir4/fileA_DS1_T2.test",
                test_data=self.small_data_1,
                mode=0o644,
                timestamp=timestamp_2,
            ),
            TestFileData(
                pathname="dir4/fileB_D2_T2.test",
                test_data=self.test_data_2,
                mode=0o644,
                timestamp=timestamp_2,
            ),
        ]

        for file_data in self.test_file_data:
            filepath = self.test_directory / file_data.pathname
            assert not filepath.exists()
            with open(filepath, "w") as out_file:
                out_file.write(file_data.test_data)
            filepath.chmod(mode=file_data.mode)
            os.utime(path=filepath, times=(file_data.timestamp, file_data.timestamp))

        self.default_options = ["--quiet"]
        # self.default_options = []

    def verify_file_data(self, *, link_counts: List[int]) -> None:
        result_link_counts = []
        for file_data in self.test_file_data:
            filepath = self.test_directory / file_data.pathname
            with open(filepath) as in_file:
                file_content = in_file.read()
            self.assertEqual(file_data.test_data, file_content)
            result_link_counts.append(get_link_count(filepath))
        self.assertEqual(link_counts, result_link_counts)

        # For debugging the tests
        # os.system(f"find {self.test_directory} -type d | sort | xargs ls -l")

    def test_hardlink(self) -> None:
        hardlink.main(self.default_options + [self.test_directory.as_posix()])
        self.assertEqual(5, hardlink.gStats.hardlinked_thisrun)
        self.verify_file_data(link_counts=[5, 2, 2, 5, 5, 5, 1, 5, 1, 1])

    def test_hardlink_contentonly(self) -> None:
        hardlink.main(
            self.default_options + ["--content-only", self.test_directory.as_posix()]
        )
        self.assertEqual(7, hardlink.gStats.hardlinked_thisrun)
        self.verify_file_data(link_counts=[5, 3, 3, 5, 5, 5, 2, 5, 2, 3])

    def test_hardlink_contentonly_min_size(self) -> None:
        hardlink.main(
            self.default_options
            + [
                "--content-only",
                "--min-size",
                "{}".format(len(self.small_data_1) + 2),
                self.test_directory.as_posix(),
            ]
        )
        self.assertEqual(6, hardlink.gStats.hardlinked_thisrun)
        self.verify_file_data(link_counts=[5, 3, 3, 5, 5, 5, 1, 5, 1, 3])


def get_link_count(path: pathlib.Path) -> int:
    return os.stat(path).st_nlink
