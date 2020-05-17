#!/usr/bin/python3 -ttu

# hardlink - Goes through a directory structure and creates hardlinks for
# files which are identical.
#
# Copyright (C) 2003 - 2019  John L. Villalovos, Hillsboro, Oregon
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc., 59
# Temple Place, Suite 330, Boston, MA  02111-1307, USA.
#
#
# ------------------------------------------------------------------------
# John Villalovos
# email: john@sodarock.com
# http://www.sodarock.com/
#
# Inspiration for this program came from the hardlink.c code. I liked what it
# did but did not like the code itself, to me it was very unmaintainable.  So I
# rewrote in C++ and then I rewrote it in python.  In reality this code is
# nothing like the original hardlink.c, since I do things quite differently.
# Even though this code is written in python the performance of the python
# version is much faster than the hardlink.c code, in my limited testing.  This
# is mainly due to use of different algorithms.
#
# Original inspirational hardlink.c code was written by:  Jakub Jelinek
# <jakub@redhat.com>
#
# ------------------------------------------------------------------------
#
# TODO(jlvillal):
#   *   Thinking it might make sense to walk the entire tree first and collect
#       up all the file information before starting to do comparisons.  Thought
#       here is we could find all the files which are hardlinked to each other
#       and then do a comparison.  If they are identical then hardlink
#       everything at once.

import argparse
import logging
import os
import re
import stat
import sys
import time
from typing import Dict, List, NamedTuple, Optional, Tuple


class FileInfo(NamedTuple):
    filename: str
    stat_info: os.stat_result


# MAX_HASHES must be a power of 2, so that MAX_HASHES - 1 will be a value with
# all bits set to 1
MAX_HASHES = 2 ** 17
assert (MAX_HASHES & (MAX_HASHES - 1)) == 0, "MAX_HASHES must be a power of 2"
MAX_HASHES_MINUS_1 = MAX_HASHES - 1


# Hash functions
# Create a hash from a file's size and time values
def hash_size_time(*, size: int, time: float) -> int:
    return (size ^ int(time)) & (MAX_HASHES_MINUS_1)


def hash_size(size: int) -> int:
    return (size) & (MAX_HASHES_MINUS_1)


def hash_value(*, size: int, time: float, notimestamp: bool) -> int:
    if notimestamp:
        return hash_size(size)
    else:
        return hash_size_time(size=size, time=time)


# If two files have the same inode and are on the same device then they are
# already hardlinked.
def is_already_hardlinked(*, st1: os.stat_result, st2: os.stat_result) -> bool:
    result = (st1.st_ino == st2.st_ino) and (st1.st_dev == st2.st_dev)
    return result


# Determine if a file is eligibile for hardlinking.  Files will only be
# considered for hardlinking if this function returns true.
def eligible_for_hardlink(
    *, st1: os.stat_result, st2: os.stat_result, args: argparse.Namespace
) -> bool:

    # Must meet the following
    # criteria:
    # * NOT already hard linked to each other
    # * sizes are equal
    # * size is greater than or equal to args.min_size
    # * file modes are equal OR we are comparing content only
    # * owner user ids are equal OR we are comparing content only
    # * owner group ids are equal OR we are comparing content only
    # * modified times are equal OR date hashing is off OR we are comparing
    #   content only
    # * device is the same

    # * sizes are equal
    if not (st1.st_size == st2.st_size):
        return False

    # * size is greater than or equal to args.min_size
    # The size should always be greater than or equal to the min size as the
    # caller should ensure that, but to be safe we check anyway.
    if st1.st_size < args.min_size:
        return False

    if not args.content_only:
        # * file modes are equal
        if not (st1.st_mode == st2.st_mode):
            return False

        # * owner user ids are equal
        if not (st1.st_uid == st2.st_uid):
            return False

        # * owner group ids are equal
        if not (st1.st_gid == st2.st_gid):
            return False

    if not args.content_only and not args.notimestamp:
        # * modified times are equal
        if not (st1.st_mtime == st2.st_mtime):
            return False

    # * device is the same
    if not (st1.st_dev == st2.st_dev):
        return False

    # * NOT already hard linked to each other
    # The files should not be hardlinked to each other as the caller should
    # ensure that, but to be safe we check anyway.
    if is_already_hardlinked(st1=st1, st2=st2):
        return False

    return True


def are_file_contents_equal(
    *, filename1: str, filename2: str, args: argparse.Namespace
) -> bool:
    """Determine if the contents of two files are equal.

    **!! This function assumes that the file sizes of the two files are
    equal.
    """

    try:
        # Open our two files
        with open(filename1, "rb") as file1:
            with open(filename2, "rb") as file2:
                gStats.did_comparison()
                if args.show_progress:
                    print(f"Comparing: {filename1}")
                    print(f"     to  : {filename2}")
                buffer_size = 1024 * 1024
                while True:
                    buffer1 = file1.read(buffer_size)
                    buffer2 = file2.read(buffer_size)
                    if buffer1 != buffer2:
                        return False

                    if not buffer1:
                        return True
    except (OSError, PermissionError) as exc:
        print("Error opening file in are_file_contents_equal()")
        print("Was attempting to open:")
        print(f"file1: {filename1}")
        print(f"file2: {filename2}")
        print("When an exception occurred: {}".format(exc))
    return False


# Determines if two files should be hard linked together.
def are_files_hardlinkable(
    *, file_info_1: FileInfo, file_info_2: FileInfo, args: argparse.Namespace
) -> bool:

    # See if the files are eligible for hardlinking
    if not eligible_for_hardlink(
        st1=file_info_1.stat_info, st2=file_info_2.stat_info, args=args
    ):
        return False

    if args.samename:
        # Check if the base filenames are the same
        basename1 = os.path.basename(file_info_1.filename)
        basename2 = os.path.basename(file_info_2.filename)
        if basename1 != basename2:
            return False

    return are_file_contents_equal(
        filename1=file_info_1.filename, filename2=file_info_2.filename, args=args
    )


# Hardlink two files together
def hardlink_files(
    *,
    sourcefile: str,
    destfile: str,
    stat_info: os.stat_result,
    args: argparse.Namespace,
) -> bool:
    # rename the destination file to save it
    temp_name = destfile + ".$$$___cleanit___$$$"
    try:
        if not args.dry_run:
            os.rename(destfile, temp_name)
    except OSError as error:
        print(f"Failed to rename: {destfile} to {temp_name}")
        print(error)
        result = False
    else:
        # Now link the sourcefile to the destination file
        try:
            if not args.dry_run:
                os.link(sourcefile, destfile)
        except:  # noqa TODO(fix this bare except)
            logging.exception(f"Failed to hardlink: {sourcefile} to {destfile}")
            # Try to recover
            try:
                os.rename(temp_name, destfile)
            except:  # noqa TODO(fix this bare except)
                logging.exception(
                    "BAD BAD - failed to rename back {} to {}".format(
                        temp_name, destfile
                    )
                )
            result = False
        else:
            # hard link succeeded
            # Delete the renamed version since we don't need it.
            if not args.dry_run:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    # If our temporary file disappears under us, ignore it.
                    # Probably an rsync is running and deleted it.
                    logging.warning(f"Temporary file vanished: {temp_name}")
                    pass
            # update our stats
            gStats.did_hardlink(sourcefile, destfile, stat_info)
            if args.show_progress:
                if args.dry_run:
                    print("Did NOT link.  Dry run")
                size = stat_info.st_size
                print(f"Linked: {sourcefile}")
                print(f"    to: {destfile}, saved {size}")
            result = True
    return result


def hardlink_identical_files(
    *, dir_entry: os.DirEntry, args: argparse.Namespace
) -> None:
    """hardlink identical files

    The purpose of this function is to hardlink files together if the files are
    the same.  To be considered the same they must be equal in the following
    criteria:
          * file size
          * file contents
          * file mode (default)
          * owner user id (default)
          * owner group id (default)
          * modified time (default)

    Also, files will only be hardlinked if they are on the same device.  This
    is because hardlink does not allow you to hardlink across file systems.

    The basic idea on how this is done is as follows:

        Walk the directory tree building up a list of the files.

     For each file, generate a simple hash based on the size and modified time.

     For any other files which share this hash make sure that they are not
     identical to this file.  If they are identical then hardlink the files.

     Add the file info to the list of files that have the same hash value.
     """

    for exclude in args.excludes:
        if re.search(exclude, dir_entry.path):
            return

    stat_info = dir_entry.stat(follow_symlinks=False)
    # Is it a regular file?
    if stat.S_ISREG(stat_info.st_mode):
        # Create the hash for the file.
        file_hash = hash_value(
            size=stat_info.st_size,
            time=stat_info.st_mtime,
            notimestamp=(args.notimestamp or args.content_only),
        )
        # Bump statistics count of regular files found.
        gStats.found_regular_file()
        if args.verbose >= 2:
            print(f"File: {dir_entry.path}")
        work_file_info = (dir_entry.path, stat_info)
        work_file_info = FileInfo(filename=dir_entry.path, stat_info=stat_info)
        if file_hash in file_hashes:
            # We have file(s) that have the same hash as our current file.
            # Let's go through the list of files with the same hash and see if
            # we are already hardlinked to any of them.
            for temp_file_info in file_hashes[file_hash]:
                if is_already_hardlinked(st1=stat_info, st2=temp_file_info.stat_info):
                    gStats.found_hardlink(
                        temp_file_info.filename,
                        dir_entry.path,
                        temp_file_info.stat_info,
                    )
                    break
            else:
                # We did not find this file as hardlinked to any other file
                # yet.  So now lets see if our file should be hardlinked to any
                # of the other files with the same hash.
                for temp_file_info in file_hashes[file_hash]:
                    if are_files_hardlinkable(
                        file_info_1=work_file_info,
                        # file_info_2=(temp_filename, temp_stat_info),
                        file_info_2=temp_file_info,
                        args=args,
                    ):
                        hardlink_files(
                            sourcefile=temp_file_info.filename,
                            destfile=dir_entry.path,
                            stat_info=temp_file_info.stat_info,
                            args=args,
                        )
                        break
                else:
                    # The file should NOT be hardlinked to any of the other
                    # files with the same hash.  So we will add it to the list
                    # of files.
                    file_hashes[file_hash].append(work_file_info)
        else:
            # There weren't any other files with the same hash value so we will
            # create a new entry and store our file.
            file_hashes[file_hash] = [work_file_info]


class cStatistics(object):
    def __init__(self) -> None:
        self.dircount = 0  # how many directories we find
        self.regularfiles = 0  # how many regular files we find
        self.comparisons = 0  # how many file content comparisons
        self.hardlinked_thisrun = 0  # hardlinks done this run
        self.hardlinked_previously = 0
        # hardlinks that are already existing
        self.bytes_saved_thisrun = 0  # bytes saved by hardlinking this run
        self.bytes_saved_previously = 0  # bytes saved by previous hardlinks
        self.hardlinkstats: List[
            Tuple[str, str]
        ] = []  # list of files hardlinked this run
        self.starttime = time.time()  # track how long it takes
        self.previouslyhardlinked: Dict[
            str, Tuple[os.stat_result, List[str]]
        ] = {}  # list of files hardlinked previously

    def found_directory(self) -> None:
        self.dircount = self.dircount + 1

    def found_regular_file(self) -> None:
        self.regularfiles = self.regularfiles + 1

    def did_comparison(self) -> None:
        self.comparisons = self.comparisons + 1

    def found_hardlink(
        self, sourcefile: str, destfile: str, stat_info: os.stat_result
    ) -> None:
        filesize = stat_info.st_size
        self.hardlinked_previously = self.hardlinked_previously + 1
        self.bytes_saved_previously = self.bytes_saved_previously + filesize
        if sourcefile not in self.previouslyhardlinked:
            self.previouslyhardlinked[sourcefile] = (stat_info, [destfile])
        else:
            self.previouslyhardlinked[sourcefile][1].append(destfile)

    def did_hardlink(
        self, sourcefile: str, destfile: str, stat_info: os.stat_result
    ) -> None:
        filesize = stat_info.st_size
        self.hardlinked_thisrun = self.hardlinked_thisrun + 1
        self.bytes_saved_thisrun = self.bytes_saved_thisrun + filesize
        self.hardlinkstats.append((sourcefile, destfile))

    def print_stats(self, args: argparse.Namespace) -> None:
        print("")
        print("Hard linking Statistics:")
        # Print out the stats for the files we hardlinked, if any
        if self.previouslyhardlinked and args.printprevious:
            keys = self.previouslyhardlinked.keys()
            print("Files Previously Hardlinked:")
            for key in sorted(keys):
                stat_info, file_list = self.previouslyhardlinked[key]
                size = stat_info.st_size
                print(f"Hardlinked together: {key}")
                for filename in file_list:
                    print(f"                   : {filename}")
                print(
                    "Size per file: {}  Total saved: {}".format(
                        size, size * len(file_list)
                    )
                )
            print()
        if self.hardlinkstats:
            if args.dry_run:
                print("Statistics reflect what would have happened if not a dry run")
            print("Files Hardlinked this run:")
            for (source, dest) in self.hardlinkstats:
                print(f"Hardlinked: {source}")
                print(f"        to: {dest}")
            print()
        print(f"Directories           : {self.dircount:,}")
        print(f"Regular files         : {self.regularfiles:,}")
        print(f"Comparisons           : {self.comparisons:,}")
        print(f"Hardlinked this run   : {self.hardlinked_thisrun:,}")
        print(
            "Total hardlinks       : {:,}".format(
                self.hardlinked_previously + self.hardlinked_thisrun
            )
        )
        print(
            "Bytes saved this run  : {:,} ({})".format(
                self.bytes_saved_thisrun, humanize_number(self.bytes_saved_thisrun)
            )
        )
        totalbytes = self.bytes_saved_thisrun + self.bytes_saved_previously
        print(
            "Total bytes saved     : {:,} ({})".format(
                totalbytes, humanize_number(totalbytes)
            )
        )
        run_time = time.time() - self.starttime
        print(
            "Total run time        : {:,.2f} seconds ({})".format(
                run_time, humanize_time(run_time)
            )
        )


def humanize_time(seconds: float) -> str:
    if seconds > 3600:  # 3600 seconds = 1 hour
        return "{:0.2f} hours".format(seconds / 3600.0)
    if seconds > 60:
        return "{:0.2f} minutes".format(seconds / 60.0)
    return f"{seconds:,.2f} seconds"


def humanize_number(number: int) -> str:
    if number > 1024 ** 4:
        return "{:0.3f} tibibytes".format(number / (1024.0 ** 4))
    if number > 1024 ** 3:
        return "{:0.3f} gibibytes".format(number / (1024.0 ** 3))
    if number > 1024 ** 2:
        return "{:0.3f} mebibytes".format(number / (1024.0 ** 2))
    if number > 1024:
        return "{:0.3f} kibibytes".format(number / 1024.0)
    return f"{number} bytes"


def parse_args(passed_args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()  # usage=usage)
    parser.add_argument(
        "directories", nargs="+", metavar="DIRECTORY", help="Directory name"
    )
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument(
        "-f",
        "--filenames-equal",
        help="Filenames have to be identical",
        action="store_true",
        dest="samename",
    )

    parser.add_argument(
        "-n", "--dry-run", help="Do NOT actually hardlink files", action="store_true"
    )

    parser.add_argument(
        "-p",
        "--print-previous",
        help="Print previously created hardlinks",
        action="store_true",
        dest="printprevious",
    )

    parser.add_argument(
        "--no-progress",
        help="Don't print progress information during execution",
        action="store_false",
        dest="show_progress",
    )

    parser.add_argument(
        "-q",
        "--no-stats",
        help="Do not print the final statistics",
        action="store_false",
        dest="printstats",
    )

    parser.add_argument(
        "-t",
        "--timestamp-ignore",
        "--ignore-timestamp",
        help="File modification times do NOT have to be identical",
        action="store_true",
        dest="notimestamp",
    )

    parser.add_argument(
        "-c",
        "--content-only",
        help="Only file contents have to match",
        action="store_true",
    )

    parser.add_argument(
        "-s",
        "--min-size",
        help="Minimum file size to perform a hard link. Must be 1 or greater",
        type=int,
        default=1,
    )

    parser.add_argument(
        "-x",
        "--exclude",
        help=(
            "Regular expression used to exclude files/dirs (may specify multiple "
            "times"
        ),
        metavar="REGEX",
        action="append",
        dest="excludes",
        default=[],
    )

    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "-v",
        "--verbose",
        help="Verbosity level. Can be used multiple times.",
        action="count",
        default=1,
    )

    verbosity_group.add_argument(
        "--quiet", help="Minimizes output", action="store_true"
    )

    args = parser.parse_args(args=passed_args)
    if args.quiet:
        args.verbose = 0
        args.show_progress = False
        args.printstats = False
    if args.min_size < 1:
        parser.error("-s/--min-size must be 1 or greater")
    args.directories = [
        os.path.abspath(os.path.expanduser(dirname)) for dirname in args.directories
    ]
    for dirname in args.directories:
        if not os.path.isdir(dirname):
            parser.print_help()
            print()
            print(f"Error: {dirname} is NOT a directory")
            sys.exit(1)
    return args


def check_python_version() -> None:
    # Make sure we have the minimum required Python version
    if sys.version_info < (3, 6, 0):
        sys.exit("ERROR: This program requires Python 3.6 or higher to run")


def setup_logger(verbose_level: int) -> None:
    log_level = logging.INFO
    if verbose_level >= 1:
        log_level = logging.DEBUG
    # Setup logging format.
    logging.basicConfig(
        format="%(levelname)s:%(filename)s:%(funcName)s():L%(lineno)d %(message)s",
        level=log_level,
    )


# Start of global declarations
debug = None
debug1 = None

gStats = cStatistics()

file_hashes: Dict[int, List[FileInfo]] = {}

VERSION = "0.7.0 - 2020-05-13 (13-May-2020)"


def main(passed_args: Optional[List[str]] = None) -> int:
    check_python_version()

    # Parse our argument list and get our list of directories
    args = parse_args(passed_args=passed_args)
    # Compile up our regexes ahead of time
    MIRROR_PL_REGEX = re.compile(r"^\.in\.")
    RSYNC_TEMP_REGEX = re.compile((r"^\..*\.\?{6,6}$"))
    # Now go through all the directories that have been added.
    # NOTE: hardlink_identical_files() will add more directories to the
    #       directories list as it finds them.
    directories = args.directories.copy()
    while directories:
        # Get the last directory in the list
        directory = directories.pop() + "/"
        if not os.path.isdir(directory):
            print(f"{directory} is NOT a directory!")
        else:
            gStats.found_directory()
            # Loop through all the files in the directory
            try:
                dir_entries = os.scandir(directory)
            except (OSError, PermissionError) as exc:
                print(
                    f"Error: Unable to do an os.scandir on: {directory}  Skipping...",
                    exc,
                )
                continue
            directories_found = []
            for dir_entry in sorted(dir_entries, key=lambda x: x.name):
                pathname = dir_entry.path
                # Look at files/dirs beginning with "."
                if dir_entry.name.startswith("."):
                    # Ignore any mirror.pl files.  These are the files that
                    # start with ".in."
                    if MIRROR_PL_REGEX.match(dir_entry.name):
                        continue
                    # Ignore any RSYNC files.  These are files that have the
                    # format .FILENAME.??????
                    if RSYNC_TEMP_REGEX.match(dir_entry.name):
                        continue
                if dir_entry.is_symlink():
                    if debug1:
                        print(f"{pathname}: is a symbolic link, ignoring")
                    continue

                if dir_entry.is_dir():
                    directories_found.append(pathname)
                    continue

                if dir_entry.stat(follow_symlinks=False).st_size < args.min_size:
                    if debug1:
                        print(f"{pathname}: Size is not large enough, ignoring")
                    continue
                hardlink_identical_files(dir_entry=dir_entry, args=args)
            # Add our found directories in reverse order because we pop them
            # off the end. Goal is to go through our directories in
            # alphabetical order.
            directories.extend(reversed(directories_found))
    if args.printstats:
        gStats.print_stats(args)
    return 0


if __name__ == "__main__":
    main()
