"""Candidate module."""


import codecs
import copy
import os
import re
import sys
from distutils.version import LooseVersion

import ansible

from ansiblelater import LOG
from ansiblelater import utils
from ansiblelater.command.review import Error
from ansiblelater.exceptions import (  # noqa
    LaterError, LaterAnsibleError
)

try:
    # Ansible 2.4 import of module loader
    from ansible.plugins.loader import module_loader
except ImportError:
    try:
        from ansible.plugins import module_loader
    except ImportError:
        from ansible.utils import module_finder as module_loader


class Candidate(object):
    """
    Meta object for all files which later has to process.

    Each file passed to later will be classified by type and
    bundled with necessary meta informations for rule processing.
    """

    def __init__(self, filename, settings={}, standards=[]):
        self.path = filename
        self.binary = False
        self.vault = False
        self.filetype = type(self).__name__.lower()
        self.expected_version = True
        self.standards = self._get_standards(settings, standards)
        self.version = self._get_version(settings)

        try:
            with codecs.open(filename, mode="rb", encoding="utf-8") as f:
                if f.readline().startswith("$ANSIBLE_VAULT"):
                    self.vault = True
        except UnicodeDecodeError:
            self.binary = True

    def _get_version(self, settings):
        if isinstance(self, RoleFile):
            parentdir = os.path.dirname(os.path.abspath(self.path))
            while parentdir != os.path.dirname(parentdir):
                meta_file = os.path.join(parentdir, "meta", "main.yml")
                if os.path.exists(meta_file):
                    path = meta_file
                    break
                parentdir = os.path.dirname(parentdir)
        else:
            path = self.path

        version = None
        version_re = re.compile(r"^# Standards:\s*([\d.]+)")

        with codecs.open(path, mode="rb", encoding="utf-8") as f:
            for line in f:
                match = version_re.match(line)
                if match:
                    version = match.group(1)

        if not version:
            version = utils.standards_latest(self.standards)
            if self.expected_version:
                if isinstance(self, RoleFile):
                    LOG.warn("%s %s is in a role that contains a meta/main.yml without a declared "
                                "standards version. "
                                "Using latest standards version %s" %
                                (type(self).__name__, self.path, version))
                else:
                    LOG.warn("%s %s does not present standards version. "
                                "Using latest standards version %s" %
                                (type(self).__name__, self.path, version))

            LOG.info("%s %s declares standards version %s" %
                     (type(self).__name__, self.path, version))

        return version

    def _get_standards(self, settings, standards):
        target_standards = []
        limits = settings.config["rules"]["filter"]

        if limits:
            for standard in standards:
                if standard.id in limits:
                    target_standards.append(standard)
        else:
            target_standards = standards

        # print(target_standards)
        return target_standards

    def review(self, settings, lines=None):
        errors = 0

        for standard in self.standards:
            if type(self).__name__.lower() not in standard.types:
                continue
            result = standard.check(self, settings.config)

            if not result:
                utils.sysexit_with_message("Standard '%s' returns an empty result object." %
                    (standard.check.__name__))

            labels = {"tag": "review", "standard": standard.name, "file": self.path, "passed": True}

            for err in [err for err in result.errors
                        if not err.lineno or utils.is_line_in_ranges(err.lineno, utils.lines_ranges(lines))]:
                err_labels = copy.copy(labels)
                err_labels["passed"] = False
                if isinstance(err, Error):
                    err_labels.update(err.to_dict())

                if not standard.version:
                    LOG.warn("{id}Best practice '{name}' not met:\n{path}:{error}".format(
                        id=standard.id, name=standard.name, path=self.path, error=err), extra=err_labels)
                elif LooseVersion(standard.version) > LooseVersion(self.version):
                    LOG.warn("{id}Future standard '{name}' not met:\n{path}:{error}".format(
                        id=standard.id, name=standard.name, path=self.path, error=err), extra=err_labels)
                else:
                    LOG.error("{id}Standard '{name}' not met:\n{path}:{error}".format(
                        id=standard.id, name=standard.name, path=self.path, error=err), extra=err_labels)
                    errors = errors + 1
            if not result.errors:
                if not standard.version:
                    LOG.info("Best practice '%s' met" % standard.name, extra=labels)
                elif LooseVersion(standard.version) > LooseVersion(self.version):
                    LOG.info("Future standard '%s' met" % standard.name, extra=labels)
                else:
                    LOG.info("Standard '%s' met" % standard.name)

        return errors

    def __repr__(self): # noqa
        return "%s (%s)" % (type(self).__name__, self.path)

    def __getitem__(self, item): # noqa
        return self.__dict__.get(item)


class RoleFile(Candidate):
    def __init__(self, filename, settings={}, standards=[]):
        super(RoleFile, self).__init__(filename, settings, standards)

        parentdir = os.path.dirname(os.path.abspath(filename))
        while parentdir != os.path.dirname(parentdir):
            role_modules = os.path.join(parentdir, "library")
            if os.path.exists(role_modules):
                module_loader.add_directory(role_modules)
                break
            parentdir = os.path.dirname(parentdir)


class Playbook(Candidate):
    pass


class Task(RoleFile):
    def __init__(self, filename, settings={}, standards=[]):
        super(Task, self).__init__(filename, settings, standards)
        self.filetype = "tasks"


class Handler(RoleFile):
    def __init__(self, filename, settings={}, standards=[]):
        super(Handler, self).__init__(filename, settings, standards)
        self.filetype = "handlers"


class Vars(Candidate):
    pass


class Unversioned(Candidate):
    def __init__(self, filename, settings={}, standards=[]):
        super(Unversioned, self).__init__(filename, settings, standards)
        self.expected_version = False


class InventoryVars(Unversioned):
    pass


class HostVars(InventoryVars):
    pass


class GroupVars(InventoryVars):
    pass


class RoleVars(RoleFile):
    pass


class Meta(RoleFile):
    pass


class Inventory(Unversioned):
    pass


class Code(Unversioned):
    pass


class Template(RoleFile):
    pass


class Doc(Unversioned):
    pass


class Makefile(Unversioned):
    pass


class File(RoleFile):
    pass


class Rolesfile(Unversioned):
    pass


def classify(filename, settings={}, standards=[]):
    parentdir = os.path.basename(os.path.dirname(filename))
    basename = os.path.basename(filename)

    if parentdir in ["tasks"]:
        return Task(filename, settings, standards)
    if parentdir in ["handlers"]:
        return Handler(filename, settings, standards)
    if parentdir in ["vars", "defaults"]:
        return RoleVars(filename, settings, standards)
    if "group_vars" in filename.split(os.sep):
        return GroupVars(filename, settings, standards)
    if "host_vars" in filename.split(os.sep):
        return HostVars(filename, settings, standards)
    if parentdir in ["meta"]:
        return Meta(filename, settings, standards)
    if parentdir in ["library", "lookup_plugins", "callback_plugins",
                     "filter_plugins"] or filename.endswith(".py"):
        return Code(filename, settings, standards)
    if "inventory" in basename or "hosts" in basename or parentdir in ["inventory"]:
        print("hosts" in filename)
        return Inventory(filename, settings, standards)
    if "rolesfile" in basename or "requirements" in basename:
        return Rolesfile(filename, settings, standards)
    if "Makefile" in basename:
        return Makefile(filename, settings, standards)
    if "templates" in filename.split(os.sep) or basename.endswith(".j2"):
        return Template(filename, settings, standards)
    if "files" in filename.split(os.sep):
        return File(filename, settings, standards)
    if basename.endswith(".yml") or basename.endswith(".yaml"):
        return Playbook(filename, settings, standards)
    if "README" in basename:
        return Doc(filename, settings, standards)
    return None
