"""Транслятор Asm в машинный код.
"""

import sys

from isa import OperationCode, write_code, Instruction, Argument, AddressMode, Register, Type, IO


INVALID_INSTRUCTION = 'Invalid instruction {}'
INVALID_ARGUMENTS_NUMBER = 'Invalid arguments number {}'


# Извлечение из строки комментариев и лишних пробелов
def simplify_line(line): return line.split(";", 1)[0].strip()


# Удаление пустых строк, комментариев и лишних пробелов
def simplify_text(text): return '\n'.join(filter(bool, [simplify_line(line) for line in text.splitlines()]))


def split_sections(text):
    assert 'section data' in text, "File must contain section data! Even if it's empty."
    assert 'section text' in text, "File must contain section text! Even if it's empty."
    # Разделение секций данных и кода
    text = text.split('section')[1:]
    data = text[0].replace('data', '', 1)
    commands = text[1].replace('text', '', 1)
    # return data text
    return simplify_text(data), simplify_text(commands)


def define_commands(code):
    """Первый проход транслятора. Преобразование текста программы в список
    инструкций и определение адресов меток.

    Особенность: транслятор ожидает, что в строке может быть либо 1 метка,
    либо 1 инструкция. Поэтому: `col` заполняется всегда 0, так как не несёт
    смысловой нагрузки.
    """

    instructions = []
    labels = {}

    for line in code.splitlines():
        instruction_number = len(instructions)

        if line.endswith(":"):  # токен содержит метку
            label = line[:-1]
            assert label not in labels, "Redefinition of label: {}".format(label)
            labels[label] = instruction_number

        else:  # токен содержит инструкцию с операндом (отделены пробелом)
            parts = line.split(" ")
            opcode = OperationCode(parts[0].lower())
            instr = Instruction(opcode, instruction_number)
            parts = parts[1:]
            assert instr.supports_arguments_number(len(parts)), INVALID_ARGUMENTS_NUMBER.format(line)
            for arg in parts:
                arg_type = arg[0]
                argument = arg[1:]
                if arg_type == ':':
                    # Метки будут расставляться на втором проходе транслятора
                    instr.add_argument(Argument(AddressMode.ABS, argument))
                elif arg_type == '@':
                    # Регистровые операции
                    assert not Register(argument.lower()) is None, 'Register is not found {}'.format(line)
                    assert instr.supports_type_of(Type.REGISTER), 'Command does not support registers {}'.format(line)
                    instr.add_argument(Argument(AddressMode.REG, argument))

                elif arg_type == '!':
                    # Абсолютная адресация
                    assert instr.supports_type_of(Type.MEM), 'Only LD and ST commands can use memory. {}'.format(line)
                    instr.add_argument(Argument(AddressMode.ABS, argument))

                elif arg_type == '\'':
                    # Создание символьного аргумента
                    assert len(argument.split("'")) == 2, "Chars must be between brackets. {}".format(line)
                    assert instr.supports_type_of(Type.REGISTER), 'Char elements used only in register operations. {}'.format(line)
                    assert len(argument[:-1]) == 1, 'One symbol = one machine word.'.format(line)
                    instr.add_argument(Argument(AddressMode.DATA, argument[:-1]))
                elif arg_type == '(':
                    argument = argument[:-1]
                    argument, offset = argument.split('|')
                    assert not Register(offset.lower()) is None, 'Register is not found {}'.format(line)
                    assert instr.supports_type_of(Type.REGISTER), 'Command does not support registers {}'.format(line)
                    assert instr.supports_type_of(Type.MEM), 'Only LD and ST commands can use memory. {}'.format(line)
                    if Register(offset.lower()) is not None:
                        instr.add_argument(Argument(AddressMode.IDR, argument, offset=Register(offset)))
                    elif int(offset):
                        instr.add_argument(Argument(AddressMode.IDR, argument, offset=int(offset)))
                else:
                    # Создание аргумента в виде числа
                    argument = arg
                    assert instr.supports_type_of(Type.REGISTER), 'Numbers are used only in register operations'
                    assert int(argument) or int(argument) == 0, 'Char elements are used only between commas. {}'.format(line)
                    instr.add_argument(Argument(AddressMode.DATA, int(argument)))

            instructions.append(instr)
    return labels, instructions


def define_data(data: str) -> list:
    # data -> structure
    addresses: dict[str, int] = {}
    variables: list[Instruction] = []
    num = 2
    for line in data.splitlines():
        variable = Instruction(OperationCode.DATA, num)
        assert len(line.split(': ', 1)) == 2, 'Incorrect variables number! Must be one! {}'.format(line)
        name, value = line.split(': ', 1)
        assert ' ' not in name, 'Variable name must avoid spaces. {}'.format(line)
        assert name not in variables, 'Data reinitialization {}'.format(line)
        if value[0] == "'":
            # Создание символьного аргумент
            value = value[1:]
            assert len(value.split("'")) == 2, "Chars must be between brackets. {}".format(line)
            value = value[:-1]
            for symbol in value:
                variable.add_argument(Argument(AddressMode.DATA, ord(symbol)))
                num += 1
        else:
            assert int(value) or value == 0, 'Char elements are used only between commas. {}'.format(line)
            variable.add_argument(Argument(AddressMode.DATA, int(value)))
        variable.add_argument(Argument(AddressMode.DATA, 0))
        num += 1

        addresses[name] = variable.index
        variables.append(variable)

    return [addresses, variables]


def linking(labels, variables, code):
    """Второй проход транслятора. В уже определённые инструкции подставляются
    адреса меток."""
    for instruction in code:
        if instruction.supports_type_of(Type.BRANCH):
            label = instruction.arguments[0].data
            assert label in labels, "Label not defined: {}".format(label)
            instruction.arguments[0].data = labels[label]
        if instruction.supports_type_of(Type.MEM):
            for argument in instruction.arguments:
                if argument.address_mode == AddressMode.ABS:
                    if argument.data.lower() in IO.keys():
                        argument.data = IO[argument.data.lower()]
                    else:
                        assert argument.data in variables, "Variable not defined: {}".format(argument.data)
                        argument.data = variables[argument.data]
                elif argument.address_mode == AddressMode.IDR:
                    assert argument.data in variables, "Variable not defined: {}".format(argument.data)
                    argument.data = variables[argument.data]
    return code


def translate(data, text):
    """Трансляция текста программы на Asm в машинный код.

    Выполняется в два прохода:

    1. Разбор текста на метки и инструкции.

    2. Подстановка адресов меток в операнды инструкции.
    """
    labels, code = define_commands(text)
    var_links, variables = define_data(data)
    code = linking(labels, var_links, code)

    return variables, code


def main(src, tar):
    """Функция запуска транслятора. Параметры -- исходный и целевой файлы."""
    with open(src, encoding="utf-8") as f: src = f.read()

    data, text = split_sections(src)
    variables, code = translate(data, text)

    write_code(tar, variables + code)
    print("source LoC:", len(text.split("\n")), "code instr:", len(code))


if __name__ == "__main__":
    assert len(sys.argv) == 3, "Wrong arguments: translator.py <input_file> <target_file>"
    _, source, target = sys.argv
    main(source, target)
