import argparse
import logging
import os
import subprocess
import sys

from .services.result_formatter import ResultFormatter
from .models import AppImage
from ._util import make_tempdir
from . import _logging
from .checks import GlibcABICheck, GlibcxxABICheck


def parse_args():
    parser = argparse.ArgumentParser(
        prog="appimagelint",
        description="Run compatibility and other checks on AppImages automatically, "
                    "and provide human-understandable feedback"
    )

    parser.add_argument("--debug",
                        dest="loglevel",
                        action="store_const", const=logging.DEBUG, default=logging.INFO,
                        help="Display debug messages")

    parser.add_argument("--log-source-location",
                        dest="log_message_locations",
                        action="store_const", const=True, default=False,
                        help="Print message locations (might be picked up by IDEs to allow for jumping to the source)")

    parser.add_argument("--log-timestamps",
                        dest="log_timestamps",
                        action="store_const", const=True, default=False,
                        help="Log timestamps (useful for debugging build times etc.)")

    parser.add_argument("--force-colors",
                        dest="force_colors",
                        action="store_const", const=True, default=False,
                        help="Force colored output")

    parser.add_argument("path",
                        nargs="+",
                        help="AppImage to review")

    args = parser.parse_args()

    return args


def run():
    args = parse_args()

    # setup
    _logging.setup(
        args.loglevel,
        with_timestamps=args.log_timestamps,
        force_colors=args.force_colors,
        log_locations=args.log_message_locations,
    )

    # get logger for CLI
    logger = _logging.make_logger("cli")

    # need up to date runtime to be able to read the mountpoint from stdout (was fixed only recently)
    # also, it's safer not to rely on the embedded runtime
    with make_tempdir() as tempdir:
        logger.info("Downloading up-to-date runtime from GitHub")

        custom_runtime = os.path.join(tempdir, "runtime")

        subprocess.check_call([
            "wget", "-q", "https://github.com/AppImage/AppImageKit/releases/download/continuous/runtime-x86_64",
            "-O", custom_runtime
        ])

        # no need to bother AppImageLauncher etc.
        os.chmod(custom_runtime, 0o755)
        with open(custom_runtime, "rb+") as f:
            f.seek(8)
            f.write(b"\x00\x00\x00")

        try:
            for path in args.path:
                logger.info("Checking AppImage {}".format(path))

                appimage = AppImage(path, custom_runtime=custom_runtime)

                kwargs = dict()
                if args.force_colors:
                    kwargs["use_colors"] = True

                formatter = ResultFormatter(**kwargs)

                for check_cls in [GlibcABICheck, GlibcxxABICheck]:
                    logger.info("Running check \"{}\"".format(check_cls.name()))
                    check = check_cls(appimage)

                    for testres in check.run():
                        check.get_logger().info(formatter.format(testres))

        except KeyboardInterrupt:
            logger.critical("process interrupted by user")
            sys.exit(2)
