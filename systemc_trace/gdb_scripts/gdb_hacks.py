# Created by ripopov
# Modified by Undo

import gdb


def is_type_compatible(val_type: gdb.Type, name: str) -> bool:
    real_type = val_type.strip_typedefs()

    if real_type.name == name:
        return True

    if real_type.code != gdb.TYPE_CODE_STRUCT:
        return False

    for field in real_type.fields():
        if field.is_base_class:
            if field.type and is_type_compatible(field.type, name):
                return True

    return False
