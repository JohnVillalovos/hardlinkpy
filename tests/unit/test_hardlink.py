import testtools

import hardlinkpy.hardlink as hardlink


class TestHardlink(testtools.TestCase):
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
