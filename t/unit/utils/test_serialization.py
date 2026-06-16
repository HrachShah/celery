import json
import pickle
import sys
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import Mock

import pytest
from kombu import Queue

from celery.utils.serialization import (STRTOBOOL_DEFAULT_TABLE, UnpickleableExceptionWrapper, ensure_serializable,
                                        find_pickleable_exception, get_pickleable_etype,
                                        get_pickleable_exception, jsonify, strtobool)

if sys.version_info >= (3, 9):
    from zoneinfo import ZoneInfo
else:
    from backports.zoneinfo import ZoneInfo


class _ModuleFine(Exception):
    """Module-level exception so pickle can resolve its class by name."""


class test_AAPickle:

    @pytest.mark.masked_modules('cPickle')
    def test_no_cpickle(self, mask_modules):
        prev = sys.modules.pop('celery.utils.serialization', None)
        try:
            import pickle as orig_pickle

            from celery.utils.serialization import pickle
            assert pickle.dumps is orig_pickle.dumps
        finally:
            sys.modules['celery.utils.serialization'] = prev


class test_ensure_serializable:

    def test_json_py3(self):
        expected = (1, "<class 'object'>")
        actual = ensure_serializable([1, object], encoder=json.dumps)
        assert expected == actual

    def test_pickle(self):
        expected = (1, object)
        actual = ensure_serializable(expected, encoder=pickle.dumps)
        assert expected == actual


class test_UnpickleExceptionWrapper:

    def test_init(self):
        x = UnpickleableExceptionWrapper('foo', 'Bar', [10, lambda x: x])
        assert x.exc_args
        assert len(x.exc_args) == 2


class test_get_pickleable_etype:

    def test_get_pickleable_etype(self):
        class Unpickleable(Exception):
            def __reduce__(self):
                raise ValueError('foo')

        assert get_pickleable_etype(Unpickleable) is Exception


class test_pickle_exceptions_narrow:
    """The except-clauses in find_pickleable_exception,
    get_pickleable_exception, get_pickleable_etype, and
    ensure_serializable are narrowed to the specific failures a pickle
    roundtrip can raise (pickle.PickleError, TypeError, AttributeError,
    RecursionError).  These tests pin that contract: in particular
    BaseException subclasses like KeyboardInterrupt and SystemExit
    must propagate, not be silently swallowed."""

    def test_find_pickleable_exception_propagates_keyboard_interrupt(self):
        class Bad(Exception):
            def __reduce__(self):
                raise KeyboardInterrupt

        try:
            find_pickleable_exception(Bad('x'))
        except KeyboardInterrupt:
            return
        raise AssertionError("KeyboardInterrupt must not be swallowed")

    def test_find_pickleable_exception_propagates_system_exit(self):
        class Bad(Exception):
            def __reduce__(self):
                raise SystemExit(2)

        try:
            find_pickleable_exception(Bad('x'))
        except SystemExit:
            return
        raise AssertionError("SystemExit must not be swallowed")

    def test_get_pickleable_exception_returns_pickleable(self):
        # _ModuleFine lives at module level so pickle can resolve its
        # class by name across the dump/load round-trip.
        e = _ModuleFine('ok')
        assert get_pickleable_exception(e) is e

    def test_get_pickleable_exception_wraps_unpickleable(self):
        class LambdaArg(Exception):
            def __init__(self, fn):
                self.fn = fn
                super().__init__(fn)
        try:
            raise LambdaArg(lambda x: x)
        except LambdaArg as e:
            result = get_pickleable_exception(e)
        assert isinstance(result, UnpickleableExceptionWrapper)

    def test_ensure_serializable_handles_unpickleable(self):
        result = ensure_serializable([1, 'a', lambda x: x, None],
                                      pickle.dumps)
        # Numeric and string items survive intact; the lambda falls back
        # to safe_repr; None is pickleable.
        assert result[0] == 1
        assert result[1] == 'a'
        assert isinstance(result[2], str) and '<lambda>' in result[2]
        assert result[3] is None

    def test_ensure_serializable_propagates_system_exit(self):
        def explode(_):
            raise SystemExit(3)
        try:
            ensure_serializable([1], explode)
        except SystemExit:
            return
        raise AssertionError("SystemExit must not be swallowed")


class test_jsonify:

    @pytest.mark.parametrize('obj', [
        Queue('foo'),
        ['foo', 'bar', 'baz'],
        {'foo': 'bar'},
        datetime.now(timezone.utc),
        datetime.now(timezone.utc).replace(tzinfo=ZoneInfo("UTC")),
        datetime.now(timezone.utc).replace(microsecond=0),
        date(2012, 1, 1),
        time(hour=1, minute=30),
        time(hour=1, minute=30, microsecond=3),
        timedelta(seconds=30),
        10,
        10.3,
        'hello',
    ])
    def test_simple(self, obj):
        assert jsonify(obj)

    def test_unknown_type_filter(self):
        unknown_type_filter = Mock()
        obj = object()
        assert (jsonify(obj, unknown_type_filter=unknown_type_filter) is
                unknown_type_filter.return_value)
        unknown_type_filter.assert_called_with(obj)

        with pytest.raises(ValueError):
            jsonify(obj)


class test_strtobool:

    @pytest.mark.parametrize('s,b',
                             STRTOBOOL_DEFAULT_TABLE.items())
    def test_default_table(self, s, b):
        assert strtobool(s) == b

    def test_unknown_value(self):
        with pytest.raises(TypeError, match="Cannot coerce 'foo' to type bool"):
            strtobool('foo')

    def test_no_op(self):
        assert strtobool(1) == 1

    def test_custom_table(self):
        custom_table = {
            'foo': True,
            'bar': False
        }

        assert strtobool("foo", table=custom_table)
        assert not strtobool("bar", table=custom_table)
