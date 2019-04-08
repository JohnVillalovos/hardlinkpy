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

from __future__ import print_function

import argparse
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple


# Hash functions
# Create a hash from a file's size and time values
def hash_size_time(*, size: int, time: float) -> int:
    return (size ^ int(time)) & (MAX_HASHES - 1)


def hash_size(size: int) -> int:
    return (size) & (MAX_HASHES - 1)


def hash_value(size: int, time: float, notimestamp: bool) -> int:
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

    if is_already_hardlinked(st1=st1, st2=st2):
        return False

    if st1.st_size < args.min_size:
        return False

    result = (
        (st1.st_size == st2.st_size)  # size is the same
        and ((st1.st_mode == st2.st_mode) or (args.contentonly))
        and (  # file mode is the same
            (st1.st_uid == st2.st_uid)  # owner user id is the same
            or (args.contentonly)  # OR we are comparing content only
        )
        and (
            (st1.st_gid == st2.st_gid)  # owner group id is the same
            or (args.contentonly)  # OR we are comparing content only
        )
        and (
            (st1.st_mtime == st2.st_mtime)  # modified time is the same
            or (args.notimestamp)  # OR date hashing is off
            or (args.contentonly)  # OR we are comparing content only
        )
        and (st1.st_dev == st2.st_dev)  # device is the same
    )
    return result


def are_file_contents_equal(
    *, filename1: str, filename2: str, args: argparse.Namespace
) -> bool:
    """Determine if the contents of two files are equal.

    **!! This function assumes that the file sizes of the two files are
    equal.
    """
    # Open our two files
    file1 = open(filename1, "rb")
    file2 = open(filename2, "rb")
    # Make sure open succeeded
    if not (file1 and file2):
        print("Error opening file in are_file_contents_equal")
        print("Was attempting to open:")
        print(f"file1: {filename1}")
        print(f"file2: {filename2}")
        result = False
    else:
        if args.verbose >= 1:
            print(f"Comparing: {filename1}")
            print(f"     to  : {filename2}")
        buffer_size = 1024 * 1024
        while 1:
            buffer1 = file1.read(buffer_size)
            buffer2 = file2.read(buffer_size)
            if buffer1 != buffer2:
                result = False
                break
            if not buffer1:
                result = True
                break
        gStats.did_comparison()
    return result


# Determines if two files should be hard linked together.
def are_files_hardlinkable(
    *,
    file_info_1: Tuple[str, os.stat_result],
    file_info_2: Tuple[str, os.stat_result],
    args: argparse.Namespace,
) -> bool:
    filename1 = file_info_1[0]
    stat_info_1 = file_info_1[1]
    filename2 = file_info_2[0]
    stat_info_2 = file_info_2[1]
    # See if the files are eligible for hardlinking
    if eligible_for_hardlink(st1=stat_info_1, st2=stat_info_2, args=args):
        # Now see if the contents of the file are the same.  If they are then
        # these two files should be hardlinked.
        if not args.samename:
            # By default we don't care if the filenames are equal
            result = are_file_contents_equal(
                filename1=filename1, filename2=filename2, args=args
            )
        else:
            # Make sure the filenames are the same, if so then compare content
            basename1 = os.path.basename(filename1)
            basename2 = os.path.basename(filename2)
            if basename1 == basename2:
                result = are_file_contents_equal(
                    filename1=filename1, filename2=filename2, args=args
                )
            else:
                result = False
    else:
        result = False
    return result


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
        if not args.dryrun:
            os.rename(destfile, temp_name)
    except OSError as error:
        print(f"Failed to rename: {destfile} to {temp_name}")
        print(error)
        result = False
    else:
        # Now link the sourcefile to the destination file
        try:
            if not args.dryrun:
                os.link(sourcefile, destfile)
        except:  # noqa TODO(fix this bare except)
            print(f"Failed to hardlink: {sourcefile} to {destfile}")
            # Try to recover
            try:
                os.rename(temp_name, destfile)
            except:  # noqa TODO(fix this bare except)
                print(
                    "BAD BAD - failed to rename back %s to %s" % (temp_name, destfile)
                )
            result = False
        else:
            # hard link succeeded
            # Delete the renamed version since we don't need it.
            if not args.dryrun:
                os.unlink(temp_name)
            # update our stats
            gStats.did_hardlink(sourcefile, destfile, stat_info)
            if args.verbose >= 1:
                if args.dryrun:
                    print("Did NOT link.  Dry run")
                size = stat_info.st_size
                print(f"Linked: {sourcefile}")
                print(f"    to: {destfile}, saved {size}")
            result = True
    return result


def hardlink_identical_files(
    *, directories: List[str], dir_entry: os.DirEntry, args: argparse.Namespace
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

    # Is it a directory?
    if dir_entry.is_dir(follow_symlinks=False):
        directories.append(dir_entry.path)
    # Is it a regular file?
    elif dir_entry.is_file(follow_symlinks=False):
        stat_info = dir_entry.stat(follow_symlinks=False)
        # Create the hash for the file.
        file_hash = hash_value(
            stat_info.st_size, stat_info.st_mtime, args.notimestamp or args.contentonly
        )
        # Bump statistics count of regular files found.
        gStats.found_regular_file()
        if args.verbose >= 2:
            print(f"File: {dir_entry.path}")
        work_file_info = (dir_entry.path, stat_info)
        if file_hash in file_hashes:
            # We have file(s) that have the same hash as our current file.
            # Let's go through the list of files with the same hash and see if
            # we are already hardlinked to any of them.
            for (temp_filename, temp_stat_info) in file_hashes[file_hash]:
                if is_already_hardlinked(st1=stat_info, st2=temp_stat_info):
                    gStats.found_hardlink(temp_filename, dir_entry.path, temp_stat_info)
                    break
            else:
                # We did not find this file as hardlinked to any other file
                # yet.  So now lets see if our file should be hardlinked to any
                # of the other files with the same hash.
                for (temp_filename, temp_stat_info) in file_hashes[file_hash]:
                    if are_files_hardlinkable(
                        file_info_1=work_file_info,
                        file_info_2=(temp_filename, temp_stat_info),
                        args=args,
                    ):
                        hardlink_files(
                            sourcefile=temp_filename,
                            destfile=dir_entry.path,
                            stat_info=temp_stat_info,
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
        print("\n")
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
                    "Size per file: %s  Total saved: %s" % (size, size * len(file_list))
                )
            print()
        if self.hardlinkstats:
            if args.dryrun:
                print("Statistics reflect what would have happened if not a dry run")
            print("Files Hardlinked this run:")
            for (source, dest) in self.hardlinkstats:
                print(f"Hardlinked: {source}")
                print(f"        to: {dest}")
            print()
        print(f"Directories           : {self.dircount}")
        print(f"Regular files         : {self.regularfiles}")
        print(f"Comparisons           : {self.comparisons}")
        print(f"Hardlinked this run   : {self.hardlinked_thisrun}")
        print(
            "Total hardlinks       : {}".format(
                self.hardlinked_previously + self.hardlinked_thisrun
            )
        )
        print(
            "Bytes saved this run  : {} ({})".format(
                self.bytes_saved_thisrun, humanize_number(self.bytes_saved_thisrun)
            )
        )
        totalbytes = self.bytes_saved_thisrun + self.bytes_saved_previously
        print(
            "Total bytes saved     : %s (%s)"
            % (totalbytes, humanize_number(totalbytes))
        )
        print("Total run time        : {} seconds".format(time.time() - self.starttime))


def humanize_number(number: int) -> str:
    if number > 1024 ** 3:
        return "%.3f gibibytes" % (number / (1024.0 ** 3))
    if number > 1024 ** 2:
        return "%.3f mebibytes" % (number / (1024.0 ** 2))
    if number > 1024:
        return "%.3f kibibytes" % (number / 1024.0)
    return "%d bytes" % number


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
        default=False,
    )

    parser.add_argument(
        "-n",
        "--dry-run",
        help="Do NOT actually hardlink files",
        action="store_true",
        dest="dryrun",
        default=False,
    )

    parser.add_argument(
        "-p",
        "--print-previous",
        help="Print previously created hardlinks",
        action="store_true",
        dest="printprevious",
        default=False,
    )

    parser.add_argument(
        "-q",
        "--no-stats",
        help="Do not print the statistics",
        action="store_false",
        dest="printstats",
        default=True,
    )

    parser.add_argument(
        "-t",
        "--timestamp-ignore",
        help="File modification times do NOT have to be identical",
        action="store_true",
        dest="notimestamp",
        default=False,
    )

    parser.add_argument(
        "-c",
        "--content-only",
        help="Only file contents have to match",
        action="store_true",
        dest="contentonly",
        default=False,
    )

    parser.add_argument(
        "-s",
        "--min-size",
        help="Minimum file size to perform a hard link. Must be 1 or greater",
        type=int,
        default=1,
    )

    parser.add_argument(
        "-v",
        "--verbose",
        help="Verbosity level. Can be used multiple times.",
        action="count",
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

    args = parser.parse_args(args=passed_args)
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


# Start of global declarations
debug = None
debug1 = None

# MAX_HASHES must be a power of 2, so that MAX_HASHES - 1 will be a value with
# all bits set to 1
MAX_HASHES = 128 * 1024
assert (MAX_HASHES & (MAX_HASHES - 1)) == 0, "MAX_HASHES must be a power of 2"

gStats = cStatistics()

file_hashes: Dict[int, List[Tuple[str, os.stat_result]]] = {}

VERSION = "0.06 - 2019-04-07 (07-Apr-2019)"


def main() -> int:
    # Parse our argument list and get our list of directories
    args = parse_args()
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
            for dir_entry in dir_entries:
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
                if debug1 and dir_entry.is_dir():
                    print(f"{pathname} is a directory!")
                hardlink_identical_files(
                    directories=directories, dir_entry=dir_entry, args=args
                )
    if args.printstats:
        gStats.print_stats(args)
    return 0


if __name__ == "__main__":
    main()
