#!/usr/bin/env python

import argparse
import json
import logging

from ansiblelater import __version__
from ansiblelater import LOG
from ansiblelater import logger
from ansiblelater.command import base
from ansiblelater.command import candidates


def main():
    parser = argparse.ArgumentParser(
        description="Validate ansible files against best pratice guideline")
    parser.add_argument("-c", "--config", dest="config_file",
                        help="Location of configuration file")
    parser.add_argument("-r", "--rules", dest="rules.standards",
                        help="Location of standards rules")
    parser.add_argument("-q", "--quiet", dest="logging.level", action="store_const",
                        const=logging.ERROR, help="Only output errors")
    parser.add_argument("-s", "--standards", dest="rules.filter", action="append",
                        help="limit standards to specific names")
    parser.add_argument("-v", dest="logging.level", action="count",
                        help="Show more verbose output")
    parser.add_argument("rules.files", nargs="*")
    parser.add_argument("--version", action="version", version="%(prog)s {}".format(__version__))

    args = parser.parse_args().__dict__

    settings = base.get_settings(args)
    config = settings.config
    # print(json.dumps(settings.config, indent=4, sort_keys=True))

    logger.update_logger(LOG, config["logging"]["level"], config["logging"]["json"])

    files = config["rules"]["files"]
    standards = base.get_standards(config["rules"]["standards"])

    errors = 0
    for filename in files:
        lines = None
        candidate = candidates.classify(filename, settings, standards)
        if candidate:
            if candidate.binary:
                LOG.info("Not reviewing binary file %s" % filename)
                continue
            if candidate.vault:
                LOG.info("Not reviewing vault file %s" % filename)
                continue
            if lines:
                LOG.info("Reviewing %s lines %s" % (candidate, lines))
            else:
                LOG.info("Reviewing all of %s" % candidate)
            errors = errors + candidate.review(settings, lines)
        else:
            LOG.info("Couldn't classify file %s" % filename)
    # return errors


if __name__ == "__main__":
    main()
