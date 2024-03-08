from __future__ import annotations

from enum import Enum

from isa import Instruction, Register, read_code, OperationCode, AddressMode, IO

import logging
import sys

# Длина машинного слова
WORD: int = 64

# Количество ячеек памяти
MEMORY = 1024


def control_machine_word(arg: int) -> int:
    # ограничение машинного слова
    while arg > 2 ** WORD: arg = -2 ** WORD + (arg - 2 ** WORD)
    while arg < -2 ** WORD: arg = 2 ** WORD - (arg + 2 ** WORD)
    return arg


class DataPath:
    class Operations(Enum):
        # Операции АЛУ
        ADD = 0
        SUB = 1
        MUL = 3
        DIV = 4
        MOD = 5

    class RegisterFile:
        # регистровый файл

        def __init__(self):
            self.registers = {
                Register.R1: 0,
                Register.R2: 0,
                Register.R3: 0,
                Register.R4: 0,
                Register.R5: 0,
                Register.R6: 0
            }
            self.first: Register = Register.R1
            self.second: Register = Register.R1
            self.output: Register = Register.R1

    class LatchSignals(Enum):
        # Управляющие сигналы
        ALU = 0
        ARG = 1
        MEM = 2
        REG = 3

    class Alu:
        # АЛУ с двумя входами
        def __init__(self):
            self.left: int = 0
            self.right: int = 0
            self.operations: dict = {
                DataPath.Operations.ADD: lambda left, right: left + right,
                DataPath.Operations.SUB: lambda left, right: left - right,
                DataPath.Operations.MUL: lambda left, right: left * right,
                DataPath.Operations.DIV: lambda left, right: left // right,
                DataPath.Operations.MOD: lambda left, right: left % right
            }

    def __init__(self, data_size, input_buffer, program):
        self.data_memory = [0] * data_size
        self.registers_file: DataPath.RegisterFile = DataPath.RegisterFile()
        self.data_size = data_size
        self.input_buffer: list[int] = input_buffer
        self.output_buffer: list[int] = []
        self.pc: int = 0
        self.addr_bus: int = 0

        self.data_alu: DataPath.Alu = DataPath.Alu()
        self.data_alu_bus: int = 0

        self.addr_alu = DataPath.Alu()
        self.addr_alu_bus: int = 0

        self.mem_bus: int = 0

        self.zero_flag: bool = False
        self.negative_flag: bool = False

        self.operation = {
            OperationCode.ADD: DataPath.Operations.ADD,
            OperationCode.SUB: DataPath.Operations.SUB,
            OperationCode.INC: DataPath.Operations.ADD,
            OperationCode.DEC: DataPath.Operations.ADD,
            OperationCode.CMP: DataPath.Operations.SUB,
            OperationCode.MUL: DataPath.Operations.MUL,
            OperationCode.DIV: DataPath.Operations.DIV,
            OperationCode.MOD: DataPath.Operations.MOD
        }

        self.load_data(program)

    def load_data(self, data):
        while data[0].instruction_code is OperationCode.DATA:
            instruction = data.pop(0)
            for i in range(len(instruction.arguments)): self.data_memory[instruction.index + i] = instruction.arguments[i].data

    def zero(self) -> bool: return self.zero_flag

    def negative(self) -> bool: return self.negative_flag

    def set_addr_alu_arguments(self, argument: int | Register):
        """Метод для эмуляции ввода данных в АЛУ, связанного счетчиком команд"""
        self.addr_alu.left = self.addr_bus
        if argument in Register: self.addr_alu.right = self.registers_file.registers[argument]
        else: self.addr_alu.right = argument

    def process_addr_alu(self, instruction: Operations):
        """Эмуляция исполнения команд в АЛУ, связанного с счетчиком команд"""
        res = control_machine_word(self.addr_alu.operations[instruction](self.addr_alu.left, self.addr_alu.right))
        self.addr_alu_bus = res

    def argument_by_address(self, operand: int | None) -> int:
        # аргумент адреса
        if operand is not None: result = control_machine_word(operand)
        else: result = self.addr_alu_bus
        assert result < MEMORY, 'Out of memory'
        return result

    def set_registers_arguments(self, out: Register = Register.R1,
                                first: Register = Register.R1,
                                second: Register = Register.R1):
        # выбор аргументов регистров
        assert (first in self.registers_file.registers and
                second in self.registers_file.registers and out in self.registers_file.registers), 'No such register'
        self.registers_file.first, self.registers_file.second, self.registers_file.output = first, second, out

    def set_data_argument(self, argument: int | None = None):
        # ввод данных в алу
        self.data_alu.left = self.registers_file.registers[self.registers_file.first]
        if argument is not None: self.data_alu.right = argument
        else: self.data_alu.right = self.registers_file.registers[self.registers_file.second]

    def process_data_alu(self, instruction: Operations):
        # исполнение команд связанных с алу
        res = control_machine_word(self.data_alu.operations[instruction](self.data_alu.left, self.data_alu.right))

        self.data_alu_bus = res
        self.zero_flag = (res == 0)
        self.negative_flag = (res < 0)

    def latch_pc(self, operand: int | None = None):
        # выбор адреса следующей исполняемой команды
        # если аргумент не передан, выполняется следующая в памяти команд
        self.pc = self.argument_by_address(operand if not operand is None else self.pc + 1)

    def latch_addr_bus(self, operand: int | None = None):
        # установка значений по адресу
        self.addr_bus = self.argument_by_address(operand)

    def latch_register(self, sel_reg: LatchSignals, argument: int | None = None):
        # Установка значения в регистр
        if sel_reg is DataPath.LatchSignals.ARG:
            assert argument is not None, 'Argument is required'
            source: int = argument
        elif sel_reg is DataPath.LatchSignals.REG:
            source = self.registers_file.registers[self.registers_file.first]
        elif sel_reg is DataPath.LatchSignals.ALU:
            source = self.data_alu_bus
        else:
            source = self.mem_bus

        self.registers_file.registers[self.registers_file.output] = source

    def read(self):
        # чтение из памяти или stdin
        if self.addr_bus == IO['stdin']:
            self.mem_bus = self.input_buffer.pop(0)
        else:
            self.mem_bus = int(self.data_memory[self.addr_bus])

    def write(self):
        # запись в память или stdout
        write_data = self.registers_file.registers[self.registers_file.second]

        if self.addr_bus == IO['stdout']:
            self.output_buffer.append(write_data)
        else:
            self.data_memory[self.addr_bus] = write_data


class ControlUnit:
    def __init__(self, program, data_path):
        self.data_path: DataPath = data_path
        self.processing_instruction: Instruction | None = None
        self.program_memory = program
        self.data_path.latch_pc(0)

    def decode_and_execute_instruction(self):
        # исполнение инструкции
        try:
            self.processing_instruction = self.program_memory[self.data_path.pc]
            opcode = self.processing_instruction.instruction_code
            if opcode is OperationCode.HLT: raise StopIteration

            elif opcode in (OperationCode.JMP, OperationCode.JZ):
                zero: bool = self.data_path.zero()
                if opcode == OperationCode.JMP or opcode == OperationCode.JZ and zero:
                    self.data_path.latch_pc(self.processing_instruction.arguments[0].data)
                else: self.data_path.latch_pc()

            elif opcode in (OperationCode.ADD, OperationCode.SUB, OperationCode.MUL, OperationCode.DIV, OperationCode.MOD):
                first_arg, second_arg = self.processing_instruction.arguments
                if second_arg.address_mode == AddressMode.REG:
                    self.data_path.set_registers_arguments(out=first_arg.data, first=first_arg.data, second=second_arg.data)
                    self.data_path.set_data_argument()
                else:
                    self.data_path.set_registers_arguments(out=Register(first_arg.data), first=Register(first_arg.data))
                    self.data_path.set_data_argument(int(second_arg.data))

                self.data_path.process_data_alu(self.data_path.operation[opcode])
                self.data_path.latch_register(DataPath.LatchSignals.ALU)
                self.data_path.latch_pc()

            elif opcode is OperationCode.CMP:
                first_arg, second_arg = self.processing_instruction.arguments
                if second_arg.address_mode == AddressMode.REG:
                    self.data_path.set_registers_arguments(first=Register(first_arg.data), second=Register(second_arg.data))
                    self.data_path.set_data_argument()
                else:
                    self.data_path.set_registers_arguments(first=Register(first_arg.data))
                    self.data_path.set_data_argument(int(second_arg.data))
                self.data_path.process_data_alu(self.data_path.operation[opcode])
                self.data_path.latch_pc()

            elif opcode is OperationCode.MOV:
                first_arg, second_arg = self.processing_instruction.arguments

                if second_arg.address_mode == AddressMode.REG:
                    self.data_path.set_registers_arguments(out=first_arg.data, first=second_arg.data)
                    self.data_path.latch_register(DataPath.LatchSignals.REG)
                else:
                    self.data_path.set_registers_arguments(out=Register(first_arg.data))
                    self.data_path.latch_register(DataPath.LatchSignals.ARG, int(second_arg.data))
                self.data_path.latch_pc()

            elif opcode in (OperationCode.INC, OperationCode.DEC):
                reg: Register = self.processing_instruction.arguments[0].data
                self.data_path.set_registers_arguments(out=reg, first=reg)
                self.data_path.set_data_argument(1 if opcode == OperationCode.INC else -1)
                self.data_path.process_data_alu(self.data_path.operation[opcode])
                self.data_path.latch_register(DataPath.LatchSignals.ALU)
                self.data_path.latch_pc()

            elif opcode is OperationCode.LD:
                first_arg, second_arg = self.processing_instruction.arguments
                self.data_path.latch_addr_bus(int(second_arg.data))

                if second_arg.address_mode == AddressMode.IDR:
                    self.data_path.set_addr_alu_arguments(second_arg.offset)
                    self.data_path.process_addr_alu(DataPath.Operations.ADD)
                    self.data_path.latch_addr_bus(self.data_path.argument_by_address(None))
                self.data_path.read()
                self.data_path.set_registers_arguments(out=Register(first_arg.data))
                self.data_path.latch_register(DataPath.LatchSignals.MEM)
                self.data_path.latch_pc()

            elif opcode is OperationCode.ST:
                first_arg, second_arg = self.processing_instruction.arguments
                self.data_path.latch_addr_bus(int(first_arg.data))
                if second_arg.address_mode == AddressMode.IDR:
                    self.data_path.set_addr_alu_arguments(first_arg.offset)
                    self.data_path.process_addr_alu(DataPath.Operations.ADD)
                    self.data_path.latch_addr_bus(self.data_path.argument_by_address(None))
                self.data_path.set_registers_arguments(second=Register(second_arg.data))
                self.data_path.write()
                self.data_path.latch_pc()

        except ValueError as error:
            raise ValueError(f'You use incorrect argument in command {self.processing_instruction.to_dict()}') from error

    def __repr__(self):
        processor_data = ("PC: {}, ADDR_BUS: {}, R1: {}, R2: {}, R3: {}, R4: {}, R5: {}, R6: {}, D_ALU_BUD: {},"
                 " A_ALU_BUD: {}, MEM_BUS: {}, N: {}, Z: {}").format(
            self.data_path.pc,
            self.data_path.addr_bus,
            self.data_path.registers_file.registers[Register.R1],
            self.data_path.registers_file.registers[Register.R2],
            self.data_path.registers_file.registers[Register.R3],
            self.data_path.registers_file.registers[Register.R4],
            self.data_path.registers_file.registers[Register.R5],
            self.data_path.registers_file.registers[Register.R6],
            self.data_path.data_alu_bus,
            self.data_path.addr_alu_bus,
            self.data_path.mem_bus,
            self.data_path.negative(),
            self.data_path.zero()
        )

        if self.processing_instruction is not None:
            instruction_data = ("INDEX: {}, OPCODE: {}, ARGS: {}"
                                .format(self.processing_instruction.index,
                                        self.processing_instruction.instruction_code.upper(),
                                        self.processing_instruction.arguments))
        else: instruction_data = ""
        return f"{processor_data} {instruction_data}"


def simulation(code, input_tokens, data_size, limit):
    """Подготовка модели и запуск симуляции процессора.

    Длительность моделирования ограничена:

    - количеством выполненных инструкций (`limit`);

    - количеством данных ввода (`input_tokens`, если ввод используется), через
      исключение `EOFError`;

    - инструкцией `Hlt`, через исключение `StopIteration`.
    """
    data_path = DataPath(data_size, input_tokens, code)
    control_unit = ControlUnit(code, data_path)
    logging.info('%s', control_unit)
    instr_counter = 0
    try:
        while True:
            assert limit > instr_counter, "To much instructions to execute!"
            control_unit.decode_and_execute_instruction()
            instr_counter += 1
            logging.info('%s', control_unit)
    except StopIteration:
        pass
    except IndexError:
        pass
    logging.debug('%s', control_unit)

    print('Instructions number: ' + str(instr_counter))

    output = ''
    for char in control_unit.data_path.output_buffer:
        output += str(char)
        if char in range(0x110000): output += '[{}]'.format(chr(char))
        output += ' '
    return output[:-1]


def main(code_file, input_file):
    """Функция запуска модели процессора. Параметры -- имена файлов с машинным
    кодом и с входными данными для симуляции.
    """
    code = read_code(code_file)
    with open(input_file, encoding="utf-8") as file:
        input_text = file.read()
        input_token = []
        for char in input_text: input_token.append(ord(char))

    print(simulation(
        code,
        input_tokens=input_token,
        data_size=MEMORY,
        limit=1000,
    ))


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    assert len(sys.argv) == 3, "Wrong arguments: machine.py <code_file> <input_file>"
    _, code_file, input_file = sys.argv
    main(code_file, input_file)
