"""Представление исходного и машинного кода.

Особенности реализации:

- Машинный код сериализуется в список JSON. Один элемент списка -- одна инструкция.
- Индекс списка соответствует:
     - адресу оператора в исходном коде;
     - адресу инструкции в машинном коде.

Пример:

```json
[{"index": 0, "instruction_name": "jz", "arguments": [{address_mode: "absolute", data: 30, offset: 0}]}]
```

где:

- `index` -- номер в машинном коде, необходим для того, чтобы понимать, куда делается условный переход;
- `instruction_name` -- строка с кодом операции (тип: `Opcode`);
- `arguments` -- аргументы инструкции (если требуется);
"""
from __future__ import annotations

import json
from enum import Enum

IO = {'stdin': 0, 'stdout': 1}


class Register(str, Enum):
    # 5 регистров процессора
    R1 = 'r1'
    R2 = 'r2'
    R3 = 'r3'
    R4 = 'r4'
    R5 = 'r5'
    R6 = 'r6'

    @classmethod
    def is_member(cls, value):
        return any(value == item.value for item in cls)

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return str(self.value)


class OperationCode(str, Enum):
    ADD = "add"
    SUB = "sub"
    MOV = "mov"
    CMP = "cmp"
    MUL = "mul"
    DIV = "div"
    MOD = "mod"

    INC = "inc"
    DEC = "dec"

    JMP = "jmp"
    JZ = "jz"

    HLT = "hlt"

    LD = "ld"
    ST = "st"

    DATA = "data"

    def __str__(self):
        return str(self.value)


class Operands(int, Enum):
    # Количество операндов, которые должны быть у команды
    TWO = 2
    ONE = 1
    NONE = 0


class Type(str, Enum):
    # Вид операции
    MEM = 'mem'
    BRANCH = 'branch'
    REGISTER = 'register'


class AddressMode(str, Enum):
    """Режимы адресации"""
    ABS = 'absolute'
    REG = 'register'
    DATA = 'data'
    IDR = 'indirect'

    def __repr__(self): return self.value


class InstructionSettings:
    def __init__(self, amount: Operands, types: list[Type]):
        self.amount = amount
        self.types: list[Type] = types


# Конфигурация ограничений операций

nop_restriction = InstructionSettings(Operands.NONE, [])

branch_restriction = InstructionSettings(Operands.ONE, [Type.BRANCH])

incdec_restriction = InstructionSettings(Operands.ONE, [Type.REGISTER])

data_restriction = InstructionSettings(Operands.TWO, [Type.REGISTER, Type.MEM])

two_restriction = InstructionSettings(Operands.TWO, [Type.REGISTER])

instruction_restriction_info: dict[OperationCode, InstructionSettings] = {

    OperationCode.HLT: nop_restriction,
    OperationCode.DATA: nop_restriction,

    OperationCode.JMP: branch_restriction,
    OperationCode.JZ: branch_restriction,

    OperationCode.INC: incdec_restriction,
    OperationCode.DEC: incdec_restriction,

    OperationCode.LD: data_restriction,
    OperationCode.ST: data_restriction,

    OperationCode.ADD: two_restriction,
    OperationCode.SUB: two_restriction,
    OperationCode.MOV: two_restriction,
    OperationCode.CMP: two_restriction,
    OperationCode.MUL: two_restriction,
    OperationCode.DIV: two_restriction,
    OperationCode.MOD: two_restriction
}


class Argument:
    # Аргумент инструкции

    def __init__(self, address_mode: AddressMode, data: int | Register | str, offset: Register | int = 0):
        self.data = data
        self.address_mode = address_mode
        self.offset = offset

    def __repr__(self):
        return '({}, {}, {})'.format(self.address_mode.value, self.data, self.offset)


class Instruction:
    # Полное описание инструкции.

    def __init__(self, instruction_code: OperationCode, index: int):
        self.instruction_code = instruction_code
        self.index = index
        self.arguments: list[Argument] = []

    def to_dict(self):
        output = dict()
        output['index'] = self.index
        output['instruction'] = self.instruction_code.value
        output['arguments'] = []
        for argument in self.arguments:
            argument_dict = dict()
            argument_dict['address_mode'] = argument.address_mode.value
            argument_dict['data'] = argument.data
            argument_dict['offset'] = argument.offset
            output['arguments'].append(argument_dict)
        return output

    def add_argument(self, arg: Argument): self.arguments.append(arg)

    def supports_type_of(self, instruction_type: Type) -> bool:
        return instruction_type in instruction_restriction_info[self.instruction_code].types

    def supports_arguments_number(self, number: int) -> bool:
        return number == instruction_restriction_info[self.instruction_code].amount.value


def write_code(filename, code: list[Instruction]):
    """Записать машинный код в файл."""
    with open(filename, "w", encoding="utf-8") as file:
        # Почему не: `file.write(json.dumps(code, indent=4))`?
        # Чтобы одна инструкция была на одну строку.
        buf = []
        for instr in code:
            buf.append(json.dumps(instr.to_dict()))
        file.write("[" + ",\n ".join(buf) + "]\n")


def read_code(filename):
    """Прочесть машинный код из файла."""
    with open(filename, encoding="utf-8") as file:
        code = json.loads(file.read())

    instructions = []

    for operation in code:
        # Конвертация строки в Opcode
        instruction = Instruction(OperationCode(operation["instruction"]), operation["index"])
        for argument in operation["arguments"]:
            instruction.add_argument(Argument(AddressMode(argument['address_mode']),
                                              argument['data'] if not AddressMode(
                                                  argument['address_mode']) is AddressMode.REG
                                              else Register(argument['data']),
                                              offset=(int(argument['offset']) if not Register.is_member(argument['offset'])
                                                      else Register(argument['offset']))))
        instructions.append(instruction)

    return instructions
