from __future__ import annotations

from typing import TypeVar
import numpy as np
import numpy.typing as npt

T1 = TypeVar("T1", bound=npt.NBitBase)
T2 = TypeVar("T2", bound=npt.NBitBase)

def add(a: np.floating[T1], b: np.integer[T2]) -> np.floating[T1 | T2]:
    return a + b

i8: np.int64
i4: np.int32
f8: np.float64
f4: np.float32

reveal_type(add(f8, i8))  # E: {Float64}
reveal_type(add(f4, i8))  # E: floating[Union[_32Bit, _64Bit]]
reveal_type(add(f8, i4))  # E: floating[Union[_64Bit, _32Bit]]
reveal_type(add(f4, i4))  # E: {Float32}
