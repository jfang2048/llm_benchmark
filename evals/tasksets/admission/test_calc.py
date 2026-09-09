"""Tests for calc. `add` is expected to fail until the bug is fixed."""

import calc


def test_add():
    assert calc.add(2, 3) == 5


def test_sub():
    assert calc.sub(5, 3) == 2


def test_mul():
    assert calc.mul(4, 5) == 20


if __name__ == "__main__":
    test_add()
    test_sub()
    test_mul()
    print("all tests passed")
