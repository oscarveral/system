#! /usr/bin/env python3
# -*- coding: utf-8; -*-

version="v.0.22.1"

"""
    Testing `asosystest` v0.22.1.

    Ampliación de Sistemas Operativos (Curso 2022/2023)
    Departamento de Ingeniería y Tecnología de Computadores
    Facultad de Informática de la Universidad de Murcia
"""


################################################################################


from enum import Enum
from itertools import compress, count
from operator import ne

# Global imports
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile


################################################################################


def info(*args):
    print("{}:".format(os.path.basename(sys.argv[0])), *args)


def panic(*args):
    info(*args)
    sys.exit(1)


################################################################################


class Range2List(argparse.Action):

    """ Helper class to parse lists of ranges. """

    def __call__(self, parser, namespace, test_ranges, option_strings=None):
        test_ranges = test_ranges.split(',')
        tests = []
        regex = re.compile('^(\d+)(?:-(\d+))?$')
        for test_range in test_ranges:
            m = regex.match(test_range)
            if not m:
                raise argparse.ArgumentTypeError('Invalid test range ' + test_range)
            start = int(m.group(1))
            end = int(m.group(2) or start)
            tests.extend(range(start, end + 1))
        setattr(namespace, self.dest, tests)


def parse_arguments():

    """ Parse command-line arguments. """

    parser = argparse.ArgumentParser(
        usage='%(prog)s [-h] [options]',
        description=f"asosys testing module ${version}.",
        epilog='Example: %(prog)s -i merge_files.json -t 1,3-5,7'
    )

    parser.add_argument(
        '-i', '--in-test-file',
        type=argparse.FileType('r'),
        dest='test_file',
        required=True,
        help='JSON file containing list of tests.')

    parser.add_argument(
        '-t', '--testids',
        type=str,
        dest='testids',
        required=False,
        default=None,
        action=Range2List,
        help='List of ranges of test IDs.')

    parser.add_argument(
        '-d', '--debug',
        dest='debug',
        required=False,
        default=False,
        action='store_true',
        help='Enable debug mode.')

    return parser.parse_args()


################################################################################


class AsoSysStatus(Enum):

    SUCCESS = 0
    FAILURE = 1
    TIMEOUT = 2
    UNKNOWN = 5


################################################################################


class AsoSysTest:

    """ ASO Syscall Tests. """

    id = 0

    @staticmethod
    def setup(config_d):

        # Initialize class variables
        AsoSysTest.desc = config_d.get('desc', 'Desc')
        AsoSysTest.timeout = config_d.get('timeout', 3)

        # Make sure the target binaries can be found in the current directory
        os.environ['PATH'] = os.environ.get('PATH', '') + ':' + os.getcwd()

        # TODO: Primitive filesystem sandboxing as chroot requires root privileges

        # Create temporary directory
        try:
            AsoSysTest.cwd = os.getcwd()
            AsoSysTest.tmp_dir = tempfile.TemporaryDirectory()
            os.chdir(AsoSysTest.tmp_dir.name)
        except OSError:
            panic("Error: Unable to create temporary directory: '{}'.".format(AsoSysTest.tmp_dir.name))
        else:
            info("Created temporary directory: '{}'.".format(AsoSysTest.tmp_dir.name))

        # Execute setup commands
        cmd = None
        try:
            cmds = config_d.get('cmds', '')
            for cmd in cmds:
                subprocess.run(cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True, shell=True)
        except OSError:
            panic("Error: Setup command not found: '{}'.".format(cmd))
        except subprocess.CalledProcessError:
            panic("Error: Setup command failed: '{}'.".format(cmd))
        else:
            info("Successfully executed setup commands '{}'.".format(cmds))

    def __init__(self, test_d, config_d):

        if not hasattr(AsoSysTest, 'id'):
            panic("Error: Call AsoSysTest.setup!")

        if not AsoSysTest.id:
            AsoSysTest.setup(config_d)
        AsoSysTest.id += 1

        # Initialize instance variables
        self.id = AsoSysTest.id

        self.cmd = test_d.get('cmd', '')
        self.stdout = test_d.get('out', '')
        self.returncode = test_d.get('rc', 0)
        self.timeout = test_d.get('timeout', AsoSysTest.timeout)

        self.status = AsoSysStatus.UNKNOWN

    def run(self):

        # Execute command
        try:
            self.res = subprocess.run(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True, text=True,
                timeout=self.timeout
            )
        except OSError:
            panic("Error: Command not found: '{}'.".format(self.cmd))
        except subprocess.CalledProcessError:
            print("{}", self.res.returncode)
            self.status = AsoSysStatus.FAILURE
        except subprocess.TimeoutExpired:
            self.status = AsoSysStatus.TIMEOUT
        else:
            if self.res.returncode == self.returncode and self.res.stdout == self.stdout:
                self.status = AsoSysStatus.SUCCESS
            else:
                self.status = AsoSysStatus.FAILURE

    def print(self, debug=False):

        if self.status == AsoSysStatus.UNKNOWN:
            panic("Test {:2}: Call self.run!".format(self.id))

        if debug: print()
        header = "{}: {}.T{:02}: ".format(os.path.basename(sys.argv[0]), AsoSysTest.desc, self.id)
        print(header, end='')

        if self.status == AsoSysStatus.SUCCESS:
            print("Result   : OK!")
        else:
            print("Result   : KO!")

        if debug:
            print(header, end='')
            print("Command  : '{:60}'".format(self.cmd[:60]))
            if self.status == AsoSysStatus.SUCCESS or self.status == AsoSysStatus.FAILURE:
                # First index where expected and produced outputs differ
                diff_pos = next(compress(count(), map(ne, self.stdout, self.res.stdout)), len(self.stdout))

                print(header, end='')
                # print("Expected : '{:60}'".format(self.stdout))
                print("{}: {}.T{:02}: Expected (rc {}): ".format(os.path.basename(sys.argv[0]), AsoSysTest.desc, self.id, self.returncode), end='')
                print('{}'.format(list(self.stdout[:diff_pos + 3])), end="")
                print(" <--" if diff_pos != len(self.stdout) else "")

                print(header, end='')
                # print("Produced : '{:60}'".format(self.res.stdout))
                print("{}: {}.T{:02}: Produced (rc {}) : ".format(os.path.basename(sys.argv[0]), AsoSysTest.desc, self.id, self.res.returncode), end='')
                print('{}'.format(list(self.res.stdout[:diff_pos + 40])),end="")
                print(" <--" if diff_pos != len(self.res.stdout) else "")

                if (self.returncode != self.res.returncode):
                    print("{}: {}.T{:02}: Return code mismatch!\n".format(os.path.basename(sys.argv[0]), AsoSysTest.desc, self.id), end='')

            elif self.status == AsoSysStatus.TIMEOUT:
                print(header, end='')
                print("Produced : TIMEOUT!")


################################################################################


def main():

    """ Main driver. """

    info("Version: {}".format(version))

    # Parse command-line arguments
    args = parse_arguments()

    # Parse JSON file
    tests_json = None
    try:
        tests_json = json.load(args.test_file)
    except ValueError:
        panic("Error: Invalid JSON format.".format(args.test_file.name))

    # Instantiate test objects
    tests = [AsoSysTest(t, tests_json['setup']) for t in tests_json['tests']]

    # Run tests
    if args.testids is None:
        for test in tests:
            test.run()
            test.print(debug=args.debug)
    else:
        if not set(args.testids) < set(range(1, len(tests)+1, 1)):
            panic("Error: Invalid list or ranges of test IDs ({}).".format(args.testids))

        for testid in args.testids:
            tests[testid-1].run()
            tests[testid-1].print(debug=args.debug)

    return 0


################################################################################


if __name__ == "__main__":
    sys.exit(main())
