from __future__ import annotations

import importlib.util
import itertools
import os
import pathlib
import re
import shutil
from collections import defaultdict
from collections.abc import Iterator
from typing import IO, TYPE_CHECKING

import pytest
import numpy as np
import numpy.typing as npt
from numpy.typing.mypy_plugin import (
    _PRECISION_DICT,
    _EXTENDED_PRECISION_LIST,
    _C_INTP,
)

try:
    from mypy import api
except ImportError:
    NO_MYPY = True
else:
    NO_MYPY = False

if TYPE_CHECKING:
    # We need this as annotation, but it's located in a private namespace.
    # As a compromise, do *not* import it during runtime
    from _pytest.mark.structures import ParameterSet

# NOTE: Mypy can have issues when running it directly over site-packages;
# run it over the numpy source instead (xref python/mypy#11477)
SRC_DATA_DIR = (
    pathlib.Path(__file__).parents[8] / "numpy" / "typing" / "tests" / "data"
)
PASS_DIR = os.path.join(SRC_DATA_DIR, "pass")
FAIL_DIR = os.path.join(SRC_DATA_DIR, "fail")
REVEAL_DIR = os.path.join(SRC_DATA_DIR, "reveal")
MISC_DIR = os.path.join(SRC_DATA_DIR, "misc")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MYPY_INI = os.path.join(DATA_DIR, "mypy.ini")
CACHE_DIR = os.path.join(DATA_DIR, ".mypy_cache")

#: A dictionary with file names as keys and lists of the mypy stdout as values.
#: To-be populated by `run_mypy`.
OUTPUT_MYPY: dict[str, list[str]] = {}


def _key_func(key: str) -> str:
    """Split at the first occurrence of the ``:`` character.

    Windows drive-letters (*e.g.* ``C:``) are ignored herein.
    """
    drive, tail = os.path.splitdrive(key)
    return os.path.join(drive, tail.split(":", 1)[0])


def _strip_filename(msg: str) -> str:
    """Strip the filename from a mypy message."""
    _, tail = os.path.splitdrive(msg)
    return tail.split(":", 1)[-1]


def strip_func(match: re.Match[str]) -> str:
    """`re.sub` helper function for stripping module names."""
    return match.groups()[1]


@pytest.mark.slow
@pytest.mark.skipif(NO_MYPY, reason="Mypy is not installed")
@pytest.fixture(scope="module", autouse=True)
def run_mypy() -> None:
    """Clears the cache and run mypy before running any of the typing tests.

    The mypy results are cached in `OUTPUT_MYPY` for further use.

    The cache refresh can be skipped using

    NUMPY_TYPING_TEST_CLEAR_CACHE=0 pytest numpy/typing/tests
    """
    if (
        os.path.isdir(CACHE_DIR)
        and bool(os.environ.get("NUMPY_TYPING_TEST_CLEAR_CACHE", True))
    ):
        shutil.rmtree(CACHE_DIR)

    for directory in (PASS_DIR, REVEAL_DIR, FAIL_DIR, MISC_DIR):
        # Run mypy
        stdout, stderr, exit_code = api.run([
            "--config-file",
            MYPY_INI,
            "--cache-dir",
            CACHE_DIR,
            directory,
        ])
        if stderr:
            pytest.fail(f"Unexpected mypy standard error\n\n{stderr}")
        elif exit_code not in {0, 1}:
            pytest.fail(f"Unexpected mypy exit code: {exit_code}\n\n{stdout}")
        stdout = stdout.replace('*', '')

        # Parse the output
        iterator = itertools.groupby(stdout.split("\n"), key=_key_func)
        OUTPUT_MYPY.update((k, list(v)) for k, v in iterator if k)


def get_test_cases(directory: str) -> Iterator[ParameterSet]:
    for root, _, files in os.walk(directory):
        for fname in files:
            short_fname, ext = os.path.splitext(fname)
            if ext in (".pyi", ".py"):
                fullpath = os.path.join(root, fname)
                yield pytest.param(fullpath, id=short_fname)


@pytest.mark.slow
@pytest.mark.skipif(NO_MYPY, reason="Mypy is not installed")
@pytest.mark.parametrize("path", get_test_cases(PASS_DIR))
def test_success(path) -> None:
    # Alias `OUTPUT_MYPY` so that it appears in the local namespace
    output_mypy = OUTPUT_MYPY
    if path in output_mypy:
        msg = "Unexpected mypy output\n\n"
        msg += "\n".join(_strip_filename(v) for v in output_mypy[path])
        raise AssertionError(msg)


@pytest.mark.slow
@pytest.mark.skipif(NO_MYPY, reason="Mypy is not installed")
@pytest.mark.parametrize("path", get_test_cases(FAIL_DIR))
def test_fail(path: str) -> None:
    __tracebackhide__ = True

    with open(path) as fin:
        lines = fin.readlines()

    errors = defaultdict(lambda: "")

    output_mypy = OUTPUT_MYPY
    assert path in output_mypy
    for error_line in output_mypy[path]:
        error_line = _strip_filename(error_line).split("\n", 1)[0]
        match = re.match(
            r"(?P<lineno>\d+): (error|note): .+$",
            error_line,
        )
        if match is None:
            raise ValueError(f"Unexpected error line format: {error_line}")
        lineno = int(match.group('lineno'))
        errors[lineno] += f'{error_line}\n'

    for i, line in enumerate(lines):
        lineno = i + 1
        if (
            line.startswith('#')
            or (" E:" not in line and lineno not in errors)
        ):
            continue

        target_line = lines[lineno - 1]
        if "# E:" in target_line:
            expression, _, marker = target_line.partition("  # E: ")
            expected_error = errors[lineno].strip()
            marker = marker.strip()
            _test_fail(path, expression, marker, expected_error, lineno)
        else:
            pytest.fail(
                f"Unexpected mypy output at line {lineno}\n\n{errors[lineno]}"
            )


_FAIL_MSG1 = """Extra error at line {}

Expression: {}
Extra error: {!r}
"""

_FAIL_MSG2 = """Error mismatch at line {}

Expression: {}
Expected error: {!r}
Observed error: {!r}
"""


def _test_fail(
    path: str,
    expression: str,
    error: str,
    expected_error: None | str,
    lineno: int,
) -> None:
    if expected_error is None:
        raise AssertionError(_FAIL_MSG1.format(lineno, expression, error))
    elif error not in expected_error:
        raise AssertionError(_FAIL_MSG2.format(
            lineno, expression, expected_error, error
        ))


def _construct_ctypes_dict() -> dict[str, str]:
    dct = {
        "ubyte": "c_ubyte",
        "ushort": "c_ushort",
        "uintc": "c_uint",
        "uint": "c_ulong",
        "ulonglong": "c_ulonglong",
        "byte": "c_byte",
        "short": "c_short",
        "intc": "c_int",
        "int_": "c_long",
        "longlong": "c_longlong",
        "single": "c_float",
        "double": "c_double",
        "longdouble": "c_longdouble",
    }

    # Match `ctypes` names to the first ctypes type with a given kind and
    # precision, e.g. {"c_double": "c_double", "c_longdouble": "c_double"}
    # if both types represent 64-bit floats.
    # In this context "first" is defined by the order of `dct`
    ret = {}
    visited: dict[tuple[str, int], str] = {}
    for np_name, ct_name in dct.items():
        np_scalar = getattr(np, np_name)()

        # Find the first `ctypes` type for a given `kind`/`itemsize` combo
        key = (np_scalar.dtype.kind, np_scalar.dtype.itemsize)
        ret[ct_name] = visited.setdefault(key, f"ctypes.{ct_name}")
    return ret


def _construct_format_dict() -> dict[str, str]:
    dct = {k.split(".")[-1]: v.replace("numpy", "numpy._typing") for
           k, v in _PRECISION_DICT.items()}

    return {
        "uint8": "numpy.uint8",
        "UInt8": "numpy.unsignedinteger[numpy._typing.8Bit]",
        "uint16": "numpy.uint16",
        "UInt16": "numpy.unsignedinteger[numpy._typing._16Bit]",
        "uint32": "numpy.uint32",
        "UInt32": "numpy.unsignedinteger[numpy._typing._32Bit]",
        "uint64": "numpy.uint64",
        "UInt64": "numpy.unsignedinteger[numpy._typing._64Bit]",
        "uint128": "numpy.uint128",
        "UInt128": "numpy.unsignedinteger[numpy._typing._128Bit]",
        "uint256": "numpy.uint256",
        "UInt256": "numpy.unsignedinteger[numpy._typing._256Bit]",
        "int8": "numpy.int8",
        "int16": "numpy.int16",
        "Int16": "numpy.signedinteger[numpy._typing._16Bit]",
        "int32": "numpy.int32",
        "Int32": "numpy.signedinteger[numpy._typing._32Bit]",
        "int64": "numpy.int64",
        "Int64": "numpy.signedinteger[numpy._typing._64Bit]",
        "int128": "numpy.int128",
        "Int128": "numpy.signedinteger[numpy._typing._128Bit]",
        "int256": "numpy.int256",
        "Int256": "numpy.signedinteger[numpy._typing._256Bit]",
        "float16": "numpy.float16",
        "Float16": "numpy.floating[numpy._typing._16Bit]",
        "float32": "numpy.float32",
        "Float32": "numpy.floating[numpy._typing._32Bit]",
        "float64": "numpy.float64",
        "Float64": "numpy.floating[numpy._typing._64Bit]",
        "float80": "numpy.float80",
        "float96": "numpy.float96",
        "float128": "numpy.float128",
        "Float128": "numpy.floating[numpy._typing._128Bit]",
        "float256": "numpy.float256",
        "complex64": "numpy.complex64",
        "complex128": "numpy.complex128",
        "complex160": "numpy.complex160",
        "complex192": "numpy.complex192",
        "complex256": "numpy.complex256",
        "complex512": "numpy.complex512",

        "ubyte": "numpy.ubyte",
        "ushort": "numpy.ushort",
        "uintc": "numpy.uintc",
        "uintp": "numpy.uintp",
        "uint": "numpy.uint",
        "ulonglong": "numpy.ulonglong",
        "byte": "numpy.byte",
        "short": "numpy.short",
        "intc": "numpy.intc",
        "intp": "numpy.intp",
        "int_": "numpy.int_",
        "longlong": "numpy.longlong",

        "half": "numpy.half",
        "single": "numpy.single",
        "double": "numpy.double",
        "longdouble": "numpy.longdouble",
        "csingle": "numpy.csingle",
        "cdouble": "numpy.cdouble",
        "clongdouble": "numpy.clongdouble",

        # numpy.typing
        "_NBitInt": dct['_NBitInt'],

        # numpy.ctypeslib
        "c_intp": f"ctypes.{_C_INTP}"
    }


#: A dictionary with all supported format keys (as keys)
#: and matching values
FORMAT_DICT: dict[str, str] = _construct_format_dict()
FORMAT_DICT.update(_construct_ctypes_dict())


def _parse_reveals(file: IO[str]) -> tuple[npt.NDArray[np.str_], list[str]]:
    """Extract and parse all ``"  # E: "`` comments from the passed
    file-like object.

    All format keys will be substituted for their respective value
    from `FORMAT_DICT`, *e.g.* ``"{float64}"`` becomes
    ``"numpy.floating[numpy._typing._64Bit]"``.
    """
    string = file.read().replace("*", "")

    # Grab all `# E:`-based comments and matching expressions
    expression_array, _, comments_array = np.char.partition(
        string.split("\n"), sep="  # E: "
    ).T
    comments = "/n".join(comments_array)

    # Only search for the `{*}` pattern within comments, otherwise
    # there is the risk of accidentally grabbing dictionaries and sets
    key_set = set(re.findall(r"\{(.*?)\}", comments))
    kwargs = {
        k: FORMAT_DICT.get(k, f"<UNRECOGNIZED FORMAT KEY {k!r}>") for
        k in key_set
    }
    fmt_str = comments.format(**kwargs)

    return expression_array, fmt_str.split("/n")


@pytest.mark.slow
@pytest.mark.skipif(NO_MYPY, reason="Mypy is not installed")
@pytest.mark.parametrize("path", get_test_cases(REVEAL_DIR))
def test_reveal(path: str) -> None:
    """Validate that mypy correctly infers the return-types of
    the expressions in `path`.
    """
    __tracebackhide__ = True

    with open(path) as fin:
        expression_array, reveal_list = _parse_reveals(fin)

    output_mypy = OUTPUT_MYPY
    assert path in output_mypy
    for error_line in output_mypy[path]:
        error_line = _strip_filename(error_line)
        match = re.match(
            r"(?P<lineno>\d+): note: .+$",
            error_line,
        )
        if match is None:
            raise ValueError(f"Unexpected reveal line format: {error_line}")
        lineno = int(match.group('lineno')) - 1
        assert "Revealed type is" in error_line

        marker = reveal_list[lineno]
        expression = expression_array[lineno]
        _test_reveal(path, expression, marker, error_line, 1 + lineno)


_REVEAL_MSG = """Reveal mismatch at line {}

Expression: {}
Expected reveal: {!r}
Observed reveal: {!r}
"""
_STRIP_PATTERN = re.compile(r"(\w+\.)+(\w+)")


def _test_reveal(
    path: str,
    expression: str,
    reveal: str,
    expected_reveal: str,
    lineno: int,
) -> None:
    """Error-reporting helper function for `test_reveal`."""
    stripped_reveal = _STRIP_PATTERN.sub(strip_func, reveal)
    stripped_expected_reveal = _STRIP_PATTERN.sub(strip_func, expected_reveal)
    if stripped_reveal not in stripped_expected_reveal:
        raise AssertionError(
            _REVEAL_MSG.format(lineno,
                               expression,
                               stripped_expected_reveal,
                               stripped_reveal)
        )


@pytest.mark.slow
@pytest.mark.skipif(NO_MYPY, reason="Mypy is not installed")
@pytest.mark.parametrize("path", get_test_cases(PASS_DIR))
def test_code_runs(path: str) -> None:
    """Validate that the code in `path` properly during runtime."""
    path_without_extension, _ = os.path.splitext(path)
    dirname, filename = path.split(os.sep)[-2:]

    spec = importlib.util.spec_from_file_location(
        f"{dirname}.{filename}", path
    )
    assert spec is not None
    assert spec.loader is not None

    test_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_module)


LINENO_MAPPING = {
    3: "uint128",
    4: "uint256",
    6: "int128",
    7: "int256",
    9: "float80",
    10: "float96",
    11: "float128",
    12: "float256",
    14: "complex160",
    15: "complex192",
    16: "complex256",
    17: "complex512",
}


@pytest.mark.slow
@pytest.mark.skipif(NO_MYPY, reason="Mypy is not installed")
def test_extended_precision() -> None:
    path = os.path.join(MISC_DIR, "extended_precision.pyi")
    output_mypy = OUTPUT_MYPY
    assert path in output_mypy

    with open(path) as f:
        expression_list = f.readlines()

    for _msg in output_mypy[path]:
        *_, _lineno, msg_typ, msg = _msg.split(":")

        msg = _strip_filename(msg)
        lineno = int(_lineno)
        expression = expression_list[lineno - 1].rstrip("\n")
        msg_typ = msg_typ.strip()
        assert msg_typ in {"error", "note"}

        if LINENO_MAPPING[lineno] in _EXTENDED_PRECISION_LIST:
            if msg_typ == "error":
                raise ValueError(f"Unexpected reveal line format: {lineno}")
            else:
                marker = FORMAT_DICT[LINENO_MAPPING[lineno]]
                _test_reveal(path, expression, marker, msg, lineno)
        else:
            if msg_typ == "error":
                marker = "Module has no attribute"
                _test_fail(path, expression, marker, msg, lineno)
