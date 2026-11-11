"""Shared test base for the daily assignments.

A function that still raises NotImplementedError is reported as skipped, not
failed, so an untouched assignment keeps the build green and a wrong answer
turns it red.
"""

import functools
import unittest


def _skip_until_written(test):
    @functools.wraps(test)
    def wrapper(self):
        try:
            test(self)
        except NotImplementedError:
            self.skipTest("not attempted yet")

    return wrapper


class DayCase(unittest.TestCase):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, member in list(vars(cls).items()):
            if name.startswith("test") and callable(member):
                setattr(cls, name, _skip_until_written(member))
