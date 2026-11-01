"""The settings file: KEY=value lines, read and never run. Nothing secret goes in it."""
import os


class SettingsError(Exception):
    """A problem with the settings, worded for the person running the command."""


def parse_settings(text):
    """The settings in the text of a settings file, as a dictionary."""
    settings = {}
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, equals, value = line.partition("=")
        key = key.strip()
        if not equals or not key:
            raise SettingsError(
                "line %d is not a KEY=value line or a # comment: %s" % (number, line)
            )
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        settings[key] = value
    return settings


def read_settings(named, default):
    """The settings from the named file, or from the default file if no file was named.

    A named file must exist. The default file need not: without it there are no settings.
    """
    path = named if named is not None else default
    if named is None and not os.path.exists(default):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise SettingsError("The settings file %s could not be read: %s" % (path, error))
    try:
        return parse_settings(text)
    except SettingsError as error:
        raise SettingsError("In the settings file %s, %s" % (path, error))
