# Created by ripopov
# Modified by Undo

import gdb


class StdVectorIterator:
    """A forward iterator through a std::vector."""

    def __init__(self, begin: gdb.Value, end: gdb.Value) -> None:
        self.cur = begin
        self.end = end

    # def next(self) -> gdb.Value:
    #    return self.__next__()

    def __next__(self) -> gdb.Value:
        if self.cur != self.end:
            val = self.cur.dereference()
            self.cur += 1
            return val
        else:
            raise StopIteration()


class StdVectorView:
    """Representation of a std::vector."""

    def __init__(self, val: gdb.Value):
        assert val.dynamic_type.name
        assert val.dynamic_type.name.startswith("std::vector<")

        self.val = val
        self.begin = val["_M_impl"]["_M_start"]
        self.end = val["_M_impl"]["_M_finish"]
        self.size = int(self.end - self.begin)

    def __iter__(self) -> StdVectorIterator:
        return StdVectorIterator(self.begin, self.end)

    def prnt(self) -> None:
        print("size ", self.size)

        for i in range(0, self.size - 1):
            print((self.begin + i).dereference().dereference().dynamic_type.name)

    def __str__(self) -> str:
        assert self.val.dynamic_type.name
        res = "vector " + self.val.dynamic_type.name + "\n"
        for ii in range(0, self.size):
            element = (self.begin + ii).dereference()
            element_type = element.dynamic_type

            if element_type.code == gdb.TYPE_CODE_PTR:
                pointed_to = element.dereference()
                assert pointed_to.dynamic_type.name
                res += "[" + str(ii) + "] type = " + pointed_to.dynamic_type.name + " *\n"
            else:
                assert element.dynamic_type.name
                res += "[" + str(ii) + "] type = " + element.dynamic_type.name + "\n"

        return res

    def __getitem__(self, key: int) -> gdb.Value:
        assert key < self.size
        return (self.begin + key).dereference()
