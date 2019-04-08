import os
import unittest.mock as mock

import testtools

import hardlinkpy.hardlink as hardlink


class TestHash(testtools.TestCase):
    def test_maxhashes_power_of_2(self) -> None:
        # MAX_HASHES must be a power of 2, so that MAX_HASHES - 1 will be a
        # value with all bits set to 1
        self.assertEqual(0, (hardlink.MAX_HASHES & (hardlink.MAX_HASHES - 1)))
        # Make sure not 0
        self.assertNotEqual(0, hardlink.MAX_HASHES)

    def test_hash_size(self) -> None:
        self.assertEqual(12, hardlink.hash_size(12))
        self.assertEqual(12, hardlink.hash_size(hardlink.MAX_HASHES + 12))
        self.assertEqual(
            hardlink.MAX_HASHES - 1, hardlink.hash_size(hardlink.MAX_HASHES - 1)
        )

    def test_hash_size_time(self) -> None:
        self.assertEqual(12, hardlink.hash_size_time(size=12, time=0.0))
        self.assertEqual(44, hardlink.hash_size_time(size=12, time=32.4))

    def test_hash_value(self) -> None:
        self.assertEqual(12, hardlink.hash_value(size=12, time=32.4, notimestamp=True))
        self.assertEqual(44, hardlink.hash_value(size=12, time=32.4, notimestamp=False))


class TestEligibleForHardlink(testtools.TestCase):
    def setUp(self) -> None:
        super().setUp()
        cmd_line = ["/tmp/hardlinkpy/directory"]
        # Make it so it doesn't care if directory doesn't exist
        with mock.patch("os.path.isdir", lambda path: True):
            self.args = hardlink.parse_args(passed_args=cmd_line)

    def make_st_result(
        self,
        *,
        st_mode: int = 0o100664,
        st_ino: int = 1,
        st_dev: int = 100,
        st_nlink: int = 1,
        st_uid: int = 1000,
        st_gid: int = 1000,
        st_size: int = 545,
        st_atime: int = 1554681319,
        st_mtime: int = 1554498398,
        st_ctime: int = 1554498398,
    ) -> os.stat_result:
        return os.stat_result(
            (
                st_mode,
                st_ino,
                st_dev,
                st_nlink,
                st_uid,
                st_gid,
                st_size,
                st_atime,
                st_mtime,
                st_ctime,
            )
        )

    def test_eligibile_for_hardlink(self) -> None:

        # Different inodes but same device
        st_file_1 = self.make_st_result(st_ino=100)
        st_file_2 = self.make_st_result(st_ino=101)

        # Identical files except for inode
        self.assertTrue(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

        # Files that are already hardlinked since same inode
        self.assertFalse(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_1, args=self.args)
        )

    def test_eligibile_for_hardlink_different_sizes(self) -> None:

        # Different inodes and different sizes
        st_file_1 = self.make_st_result(st_ino=100, st_size=1024)
        st_file_2 = self.make_st_result(st_ino=101, st_size=2048)

        # Different size files, should be False
        self.assertFalse(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

    def test_eligibile_for_hardlink_different_dev(self) -> None:

        # Different inodes and different devices
        st_file_1 = self.make_st_result(st_ino=100, st_dev=100)
        st_file_2 = self.make_st_result(st_ino=101, st_dev=200)

        # Different size files, should be False
        self.assertFalse(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

    def test_eligibile_for_hardlink_different_modes(self) -> None:

        # Different inodes and different modes
        st_file_1 = self.make_st_result(st_ino=100, st_mode=0o644)
        st_file_2 = self.make_st_result(st_ino=101, st_mode=0o755)

        # Different file modes, should be False
        self.assertFalse(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

        self.args.contentonly = True
        # Different file modes, contentonly=True, should be True
        self.assertTrue(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

    def test_eligibile_for_hardlink_different_uid(self) -> None:

        # Different inodes and different UIDs
        st_file_1 = self.make_st_result(st_ino=100, st_uid=1000)
        st_file_2 = self.make_st_result(st_ino=101, st_uid=2000)

        # Different UIDs should be False
        self.assertFalse(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

        self.args.contentonly = True
        # Different UIDs, contentonly=True, should be True
        self.assertTrue(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

    def test_eligibile_for_hardlink_different_gid(self) -> None:

        # Different inodes and different GIDs
        st_file_1 = self.make_st_result(st_ino=100, st_gid=1000)
        st_file_2 = self.make_st_result(st_ino=101, st_gid=2000)

        # Different GIDs should be False
        self.assertFalse(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

        self.args.contentonly = True
        # Different GIDs, contentonly=True, should be True
        self.assertTrue(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

    def test_eligibile_for_hardlink_different_mtime(self) -> None:

        # Different inodes and different GIDs
        st_file_1 = self.make_st_result(st_ino=100, st_mtime=1000)
        st_file_2 = self.make_st_result(st_ino=101, st_mtime=2000)

        # Different mtimes should be False
        self.assertFalse(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

        self.args.contentonly = True
        self.args.notimestamp = False
        # Different mtimes, contentonly=True, should be True
        self.assertTrue(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

        self.args.contentonly = False
        self.args.notimestamp = True
        # Different mtimes, contentonly=True, should be True
        self.assertTrue(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

    def test_eligibile_for_hardlink_min_size(self) -> None:

        # File must be at least 1024 bytes in size
        self.args.min_size = 1024

        # Different inodes but size is too small
        st_small_1 = self.make_st_result(st_ino=100, st_size=1023)
        st_small_2 = self.make_st_result(st_ino=101, st_size=1023)

        self.assertFalse(
            hardlink.eligible_for_hardlink(
                st1=st_small_1, st2=st_small_2, args=self.args
            )
        )

        # Files are large enough
        st_file_1 = self.make_st_result(st_ino=101, st_size=1024)
        st_file_2 = self.make_st_result(st_ino=102, st_size=1024)

        self.assertTrue(
            hardlink.eligible_for_hardlink(st1=st_file_1, st2=st_file_2, args=self.args)
        )

    def test_already_hardlinked_same_device(self) -> None:
        # Different inodes but same device
        st_file_1 = self.make_st_result(st_ino=100)
        st_file_2 = self.make_st_result(st_ino=101)

        # Identical files except for inode
        self.assertFalse(hardlink.is_already_hardlinked(st1=st_file_1, st2=st_file_2))

        # Files that are already hardlinked since same inode
        self.assertTrue(hardlink.is_already_hardlinked(st1=st_file_1, st2=st_file_1))

    def test_already_hardlinked_different_device(self) -> None:
        # Same inode but different device
        st_file_1 = self.make_st_result(st_ino=100, st_dev=1)
        st_file_2 = self.make_st_result(st_ino=100, st_dev=2)

        # Identical files except for different device, not hardlinked
        self.assertFalse(hardlink.is_already_hardlinked(st1=st_file_1, st2=st_file_2))
