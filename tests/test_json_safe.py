import numpy as np

from app.utils.json_safe import to_jsonable


def test_ndarray_and_scalar():
    assert to_jsonable(np.array([1.0, 2.0])) == [1.0, 2.0]
    assert to_jsonable(np.float64(3.14)) == 3.14
    assert to_jsonable({"x": np.array([1]), "y": np.int32(2)}) == {"x": [1], "y": 2}
