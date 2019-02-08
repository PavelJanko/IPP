import re
import xml.etree.ElementTree
import sys


# Funkce pro vypis chybove zpravy a ukonceni programu s odpovidajicim chybovym kodem
def exit_with_error(message, code):
    print(message, file=sys.stderr)
    sys.exit(code)


# Trida pro argument instrukce
class Argument:
    # Konstruktor
    def __init__(self, arg_elem):
        if arg_elem is None:
            exit_with_error('Argument ma spatny nazev elementu', 31)

        self.type = arg_elem.get('type')
        self.value = self.set_value(arg_elem)

    # Setter pro hodnotu, ktery overuje lexikalni spravnost atributu
    def set_value(self, arg_elem):
        value = arg_elem.text

        # Kontrola argumentu typu type
        if self.type == 'type' and value in ['int', 'bool', 'string']:
            pass
        # Kontrola argumentu booleovskeho typu
        elif self.type == 'bool' and value in ['true', 'false']:
            if value == 'true':
                return True
            else:
                return False
        # Kontrola argumentu celociselneho typu
        elif self.type == 'int' and (value.count('-') < 2 or value.count('+') < 2):
            if value.isdigit():
                return int(value)
            else:
                exit_with_error('Argument instrukce ma spatny tvar', 32)
        # Kontrola argumentu retezcoveho typu
        elif self.type == 'string':
            if value is not None and '#' not in value and ' ' not in value:
                # Cyklus pro zpracovani escape sekvenci
                for index, part in enumerate(value.split('\\')):
                    if index == 0:
                        continue
                    if not part[:3].isdigit():
                        exit_with_error('Argument instrukce ma spatny tvar', 32)
                    else:
                        value = value.replace("\\" + part[:3], chr(int(part[:3])))
                return value
            elif value is None:
                return ''
        # Kontrola argumentu typu promenna (vcetne ramce)
        elif self.type == 'var':
            parts = value.split('@')
            if (parts[0] not in ['GF', 'LF', 'TF'] or parts[1][0].isdigit() or
                    not re.match(r"^[a-zA-Z0-9-_$&*%]+$", parts[1])):
                exit_with_error('Argument instrukce ma spatny tvar', 32)
        # Kontrola argumentu typu navesti (aplikuje se stejne podminky jako na promennou,
        # ale neni treba kontrolovat tvar ramce
        elif self.type == 'label' and re.match(r"^[a-zA-Z0-9-_$&*%]+$", value):
            pass
        else:
            exit_with_error('Argument instrukce ma spatny tvar', 32)
        return value


# Trida pro zpracovani jednotlivych instrukci XML souboru
class Instruction:
    def __init__(self, instr_elem):
        self.args = []

        if len(instr_elem) > 3:
            exit_with_error('Instrukce nemuze mit vice nez 3 argumenty', 52)
        # Je potreba se prizpusobit faktu, ze v XML muze byt poradi elementu poprehazene
        for index in range(1, len(instr_elem) + 1):
            arg_helper = instr_elem.findall('arg' + str(index))
            if len(arg_helper) == 1:
                self.args.append(Argument(arg_helper[0]))
            else:
                exit_with_error('Argument ma spatny nazev elementu', 31)

        self.opcode = instr_elem.get('opcode')
        self.order = self.set_order(instr_elem)

    # Staticka metoda pro nastaveni hodnoty order podle XML souboru
    @staticmethod
    def set_order(instr_elem):
        order = instr_elem.get('order')
        if order.isdigit() and int(order) > 0:
            return int(order)
        else:
            exit_with_error('Instrukce ma spatnou hodnotu atributu order', 31)

    def check_args(self, arguments):
        if len(self.args) != len(arguments):
            exit_with_error('Instrukce ma spatny pocet argumentu', 32)

        for index, arg in enumerate(arguments):
            arg_type = self.args[index].type
            if ((arg == 'var' and arg_type != 'var') or
                    (arg == 'symb' and arg_type not in ['var', 'int', 'bool', 'string']) or
                    (arg == 'label' and arg_type != 'label') or
                    (arg == 'type' and arg_type != 'type')):
                exit_with_error('Operand je spatneho typu', 52)


# Trida pro provedeni jednotlivych instrukci v XML souboru
class Interpreter:
    def __init__(self):
        self.curr_ins = 1

        # Definice ramcu spolu se zasobnikem volani, datovym zasobnikem a seznamem navesti
        self.global_frame = {}
        self.local_frame_stack = []
        self._temp_frame = None

        self._labels = {}
        self.call_stack = []
        self.data_stack = []

    # Pomocna funkce pro pristup k promennym v ramcich
    def frame(self, arg):
        frame_id = arg.split('@')[0]

        if frame_id == 'GF':
            return self.global_frame
        elif frame_id == 'LF':
            return self.local_frame
        elif frame_id == 'TF':
            return self.temp_frame
        else:
            exit_with_error('Neplatne oznaceni ramce', 54)

    # Funkce pro ziskani hodnoty promenne z ramce
    def get_var_value(self, arg):
        try:
            return self.frame(arg)[arg.split('@', 1)[1]]
        except KeyError:
            exit_with_error('Promenna neexistuje', 54)

    # Funkce pro nastaveni hodnoty promenne v ramci
    def set_var_value(self, arg, value):
        self.frame(arg)[arg.split('@', 1)[1]] = value

    # Funkce pro pristup k lokalnimu ramci, ktera automaticky bud vraci ramec na vrcholu zasobniku, nebo vypise chybu
    # v pripade, ze je zasobnik prazdny
    @property
    def local_frame(self):
        if not len(self.local_frame_stack):
            exit_with_error('Zasobnik ramcu je prazdny', 55)
        return self.local_frame_stack[-1]

    # Funkce pro pristup k docasnemu ramci (jelikoz se jedna o slovnik, tak se pouze zjistuje, jestli je prazdny)
    @property
    def temp_frame(self):
        if self._temp_frame is None:
            exit_with_error('Docasny ramec neni inicializovan', 55)
        return self._temp_frame

    # Funkce pro pristup k urcite instrukci v slovniku navesti
    def labels(self, key):
        if key not in self._labels:
            exit_with_error('Navesti neni definovano', 56)
        return self._labels

    # Hlavni funkce pro provedeni instrukce
    # Na zacatku kodu pro kazdou instrukci se provede overeni, zdali ma spravny pocet a typ argumentu
    def execute(self, instr):
        # Prace s ramci, volani funkci
        # MOVE <var> <symb>
        if instr.opcode == 'MOVE':
            instr.check_args(['var', 'symb'])
            dst_var_name = instr.args[0].value
            src_symb = instr.args[1].value

            if instr.args[1].type == 'var':
                src_symb = self.get_var_value(src_symb)
            if src_symb is not None:
                self.set_var_value(dst_var_name, src_symb)
            else:
                exit_with_error('Pokus o presunuti obsahu neinicializovane promenne', 56)
        # CREATEFRAME
        elif instr.opcode == 'CREATEFRAME':
            instr.check_args([])
            if self._temp_frame is None:
                self._temp_frame = {}
            else:
                self.temp_frame.clear()
        # PUSHFRAME
        elif instr.opcode == 'PUSHFRAME':
            instr.check_args([])
            # Vsechny promenne v Pythonu se predavaji funkci skrz referenci, takze musim poslat kopii
            self.local_frame_stack.append(self._temp_frame.copy())
            self._temp_frame = None
        # POPFRAME
        elif instr.opcode == 'POPFRAME':
            instr.check_args([])
            self._temp_frame = self.local_frame
            del self.local_frame_stack[-1]
        # DEFVAR <var>
        elif instr.opcode == 'DEFVAR':
            instr.check_args(['var'])
            var_name = instr.args[0].value

            # Program resi redefinici promennych tak, ze jednoduse prepise stary obsah novym (viz dokumentace)
            self.set_var_value(var_name, None)
        # CALL <label>
        elif instr.opcode == 'CALL':
            instr.check_args(['label'])
            self.call_stack.append(self.curr_ins + 1)
            self.curr_ins = self.labels(instr.args[0].value)[instr.args[0].value]
            # Funkce se musi ukoncit predcasne, aby nedoslo k inkrementaci poradi zpracovavane instrukce, protoze
            # tuto hodnotu prave instrukce CALL nastavuje
            return
        # RETURN
        elif instr.opcode == 'RETURN':
            instr.check_args([])
            if not len(self.call_stack):
                exit_with_error('Zasobnik volani je prazdny', 56)
            self.curr_ins = self.call_stack[-1]
            del self.call_stack[-1]
            # Predcasne ukonceni ze stejneho duvodu jako u instrukce vyse
            return
        # Prace s datovym zasobnikem
        # PUSHS <symb>
        elif instr.opcode == 'PUSHS':
            instr.check_args(['symb'])
            var_val = instr.args[0].value
            if instr.args[0].type == 'var':
                self.data_stack.append(self.get_var_value(var_val))
            else:
                self.data_stack.append(var_val)
        # POPS <var>
        elif instr.opcode == 'POPS':
            instr.check_args(['var'])
            if not len(self.data_stack):
                exit_with_error('Datovy zasobnik je prazdny', 56)
            self.set_var_value(instr.args[0].value, self.data_stack[-1])
            del self.data_stack[-1]
        # Aritmeticke, relacni, booleovske a konverzni instrukce
        # ADD/SUB/MUL/IDIV <var> <symb> <symb>
        elif instr.opcode == 'ADD' or instr.opcode == 'SUB' or instr.opcode == 'MUL' or instr.opcode == 'IDIV':
            dst_var_name = instr.args[0].value
            first_operand = instr.args[1].value
            second_operand = instr.args[2].value

            if instr.args[1].type == 'var':
                first_operand = self.get_var_value(first_operand)
            if instr.args[2].type == 'var':
                second_operand = self.get_var_value(second_operand)
            # Pro zamezeni implicitnich konverzi v podminkach pouzivam funkce isinstance, ktera porovna datovy typ
            # objektu
            if not isinstance(first_operand, int) or not isinstance(second_operand, int):
                exit_with_error('Operandy aritmetickych operaci musi byt celociselneho typu', 53)
            # Osetreni deleni nulou
            if instr.opcode == 'IDIV' and second_operand == 0:
                exit_with_error('Deleni nulou', 57)

            if instr.opcode == 'ADD':
                self.set_var_value(dst_var_name, first_operand + second_operand)
            elif instr.opcode == 'SUB':
                self.set_var_value(dst_var_name, first_operand - second_operand)
            elif instr.opcode == 'MUL':
                self.set_var_value(dst_var_name, first_operand * second_operand)
            else:
                self.set_var_value(dst_var_name, first_operand // second_operand)
        # LT/GT/EQ <var> <symb> <symb>
        elif instr.opcode == 'LT' or instr.opcode == 'GT' or instr.opcode == 'EQ':
            dst_var_name = instr.args[0].value
            first_operand = instr.args[1].value
            second_operand = instr.args[2].value
            result = None

            if instr.args[1].type == 'var':
                first_operand = self.get_var_value(first_operand)
            if instr.args[2].type == 'var':
                second_operand = self.get_var_value(second_operand)
            # Pro retezec i celociselny typ se pouziva stejne porovnani proto, ze Python implicitne retezce porovnava
            # lexikograficky
            if isinstance(first_operand, int) and isinstance(second_operand, int)\
                    or isinstance(first_operand, str) and isinstance(second_operand, str):
                if instr.opcode == 'LT':
                    result = first_operand < second_operand
                elif instr.opcode == 'GT':
                    result = first_operand > second_operand
            # Pro booleovsky typ ma pravda vzdy vetsi hodnotu
            elif isinstance(first_operand, bool) and isinstance(second_operand, bool):
                if instr.opcode == 'LT':
                    if first_operand == second_operand or first_operand and not second_operand:
                        result = False
                    elif not first_operand and second_operand:
                        result = True
                elif instr.opcode == 'GT':
                    if first_operand == second_operand or not first_operand and second_operand:
                        result = False
                    elif first_operand and not second_operand:
                        result = True
            else:
                exit_with_error('Operandy operace jsou neplatneho typu', 53)
            if instr.opcode == 'EQ':
                result = first_operand == second_operand
            self.set_var_value(dst_var_name, result)
        # AND/OR <var> <symb> <symb>
        elif instr.opcode == 'AND' or instr.opcode == 'OR':
            dst_var_name = instr.args[0].value
            first_operand = instr.args[1].value
            second_operand = instr.args[2].value

            if instr.args[1].type == 'var':
                first_operand = self.get_var_value(first_operand)
            if instr.args[2].type == 'var':
                second_operand = self.get_var_value(second_operand)
            # Operace lze provadet pouze pro booleovske operatory (to stejne plati pro NOT nize)
            if not isinstance(first_operand, bool) or not isinstance(second_operand, bool):
                exit_with_error('Operandy logickych operaci musi byt booleovskeho typu', 53)
            if instr.opcode == 'AND':
                result = first_operand and second_operand
            else:
                result = first_operand and second_operand
            self.set_var_value(dst_var_name, result)
        #  NOT <var> <symb>
        elif instr.opcode == 'NOT':
            dst_var_name = instr.args[0].value
            first_operand = instr.args[1].value

            if instr.args[1].type == 'var':
                first_operand = self.get_var_value(first_operand)
            if not isinstance(first_operand, bool):
                exit_with_error('Operandy logickych operaci musi byt booleovskeho typu', 53)
            self.set_var_value(dst_var_name, not first_operand)
        # INT2CHAR <var> <symb>
        elif instr.opcode == 'INT2CHAR':
            instr.check_args(['var', 'symb'])
            dst_var_name = instr.args[0].value
            src_symb = instr.args[1].value

            if instr.args[1].type == 'var':
                src_symb = self.get_var_value(src_symb)
            if not isinstance(src_symb, int):
                exit_with_error('Operand operace musi byt celociselneho typu', 53)
            # Maximalni ASCII hodnota, kterou lze v Pythonu prekonvertovat, je 1114111
            if src_symb <= 1114111:
                self.set_var_value(dst_var_name, chr(src_symb))
            else:
                exit_with_error('Ciselna hodnota pro konverzi je neplatna', 58)
        # STRI2INT <var> <symb> <symb>
        elif instr.opcode == 'STRI2INT':
            instr.check_args(['var', 'symb', 'symb'])
            dst_var_name = instr.args[0].value
            src_symb = instr.args[1].value
            pos_symb = instr.args[2].value

            if instr.args[1].type == 'var':
                src_symb = self.get_var_value(src_symb)
            if instr.args[2].type == 'var':
                pos_symb = self.get_var_value(pos_symb)
            if not isinstance(src_symb, str) or not isinstance(pos_symb, int):
                exit_with_error('Operandy operace jsou neplatneho typu', 53)
            if 0 <= pos_symb < len(src_symb):
                self.set_var_value(dst_var_name, ord(src_symb[pos_symb]))
            else:
                exit_with_error('Zadana pozice znaku je neplatna', 58)
        # Vstupne-vystupni instrukce
        # READ <var> <type>
        elif instr.opcode == 'READ':
            instr.check_args(['var', 'type'])
            dst_var_name = instr.args[0].value
            type_val = instr.args[1].value

            try:
                input_val = input('Insert value of type ' + type_val + ': ')
            # Osetreni pripadu, kdy je funkci vestavene funkci input predana hodnota konce souboru
            except EOFError:
                input_val = None

            if type_val == 'bool':
                if input_val is not None and input_val.lower() == 'true':
                    self.set_var_value(dst_var_name, 'true')
                else:
                    self.set_var_value(dst_var_name, 'false')
            elif type_val == 'int':
                if input_val is not None and input_val.isdigit():
                    self.set_var_value(dst_var_name, int(input_val))
                else:
                    self.set_var_value(dst_var_name, 0)
            else:
                if input_val is not None:
                    self.set_var_value(dst_var_name, input_val)
                else:
                    self.set_var_value(dst_var_name, '')
        # WRITE <symb>
        elif instr.opcode == 'WRITE':
            instr.check_args(['symb'])
            src_arg_value = instr.args[0].value

            if instr.args[0].type == 'var':
                src_arg_value = self.get_var_value(src_arg_value)
            # V pripade, ze se jedna o booleovsky typ, musi se vypsat hodnota malymi pismeny, nikoliv pocatecni velkym
            if isinstance(src_arg_value, bool):
                if src_arg_value:
                    src_arg_value = 'true'
                else:
                    src_arg_value = 'false'

            print(src_arg_value)
        # Prace s retezci
        # CONCAT <var> <symb> <symb>
        elif instr.opcode == 'CONCAT':
            instr.check_args(['var', 'symb', 'symb'])
            first_part = instr.args[1].value
            second_part = instr.args[2].value

            if instr.args[1].type == 'var':
                first_part = self.get_var_value(first_part)
            if instr.args[2].type == 'var':
                second_part = self.get_var_value(second_part)
            if isinstance(first_part, str) and isinstance(first_part, str):
                self.set_var_value(instr.args[0].value, first_part + second_part)
            else:
                exit_with_error('Operandy operace musi byt retezcoveho typu', 53)
        # STRLEN <var> <symb>
        elif instr.opcode == 'STRLEN':
            instr.check_args(['var', 'symb'])
            dst_var_name = instr.args[0].value
            src_symb = instr.args[1].value

            if instr.args[1].type == 'var':
                src_symb = self.get_var_value(src_symb)
            if isinstance(src_symb, str):
                self.set_var_value(dst_var_name, len(src_symb))
            else:
                exit_with_error('Operand operace musi byt retezcoveho typu', 53)
        # GETCHAR <var> <symb> <symb>
        elif instr.opcode == 'GETCHAR':
            instr.check_args(['var', 'symb', 'symb'])
            dst_var_name = instr.args[0].value
            src_symb = instr.args[1].value
            pos_symb = instr.args[2].value

            if instr.args[1].type == 'var':
                src_symb = self.get_var_value(src_symb)
            if instr.args[2].type == 'var':
                pos_symb = self.get_var_value(pos_symb)
            if not isinstance(src_symb, str) or not isinstance(pos_symb, int):
                exit_with_error('Operandy operace jsou neplatneho typu', 53)
            if 0 <= pos_symb < len(src_symb):
                self.set_var_value(dst_var_name, src_symb[pos_symb])
            else:
                exit_with_error('Zadana pozice znaku je neplatna', 58)
        # SETCHAR <var> <symb> <symb>
        elif instr.opcode == 'SETCHAR':
            instr.check_args(['var', 'symb', 'symb'])
            dst_var_name = instr.args[0].value
            pos_symb = instr.args[1].value
            char_symb = instr.args[2].value

            if instr.args[1].type == 'var':
                pos_symb = self.get_var_value(pos_symb)
            if instr.args[2].type == 'var':
                char_symb = self.get_var_value(char_symb)
            if not isinstance(pos_symb, int) or not isinstance(char_symb, str):
                exit_with_error('Operandy operace jsou neplatneho typu', 53)
            if 0 <= pos_symb < len(self.get_var_value(dst_var_name)):
                tmp_list = list(self.get_var_value(dst_var_name))
                tmp_list[pos_symb] = char_symb[0]
                self.set_var_value(dst_var_name, ''.join(tmp_list))
            else:
                exit_with_error('Zadana pozice znaku je neplatna', 58)
        # Prace s typy
        # TYPE <var> <symb>
        elif instr.opcode == 'TYPE':
            dst_var_name = instr.args[0].value
            type_symb = instr.args[1].value
            ins_value = ''

            if instr.args[1].type == 'var':
                type_symb = self.get_var_value(type_symb)

                if isinstance(type_symb, int) or str(type_symb).isdigit():
                    ins_value = 'int'
                elif isinstance(type_symb, bool) or str(type_symb).lower() == 'true' \
                        or str(type_symb).lower() == 'false':
                    ins_value = 'bool'
                elif isinstance(type_symb, str):
                    ins_value = 'string'
            else:
                ins_value = instr.args[1].type

            self.set_var_value(dst_var_name, ins_value)
        # Instrukce pro rizeni toku programu
        # LABEL <label>
        elif instr.opcode == 'LABEL':
            instr.check_args(['label'])
            self._labels[instr.args[0].value] = instr.order
        # JUMP <label>
        elif instr.opcode == 'JUMP':
            instr.check_args(['label'])
            self.curr_ins = self.labels(instr.args[0].value)[instr.args[0].value]
            return
        # JUMPIFEQ/JUMPIFNEQ <label> <symb> <symb>
        elif instr.opcode == 'JUMPIFEQ' or instr.opcode == 'JUMPIFNEQ':
            instr.check_args(['label', 'symb', 'symb'])
            first_part = instr.args[1].value
            second_part = instr.args[2].value
            if instr.args[1].type == 'var':
                first_part = self.get_var_value(first_part)
            if instr.args[2].type == 'var':
                second_part = self.get_var_value(second_part)
            if (instr.opcode == 'JUMPIFEQ' and first_part == second_part
                    or instr.opcode == 'JUMPIFNEQ' and first_part != second_part):
                self.curr_ins = self.labels(instr.args[0].value)[instr.args[0].value]
                # Opet musim funkci ukoncit predcasne, protoze instrukce nastavuje poradi zpracovavane instrukce
                return
        # DPRINT <symb>
        elif instr.opcode == 'DPRINT':
            instr.check_args(['symb'])
            src_symb = instr.args[0].val

            if instr.args[0].type == 'var':
                src_symb = self.get_var_value(src_symb)
            print(src_symb, file=sys.stderr)
        # BREAK
        elif instr.opcode == 'BREAK':
            instr.check_args([])
            print('Poradi prave zpracovane instrukce: ' + str(self.curr_ins), file=sys.stderr)

            print('Obsah globalniho ramce:', file=sys.stderr)
            for item in self.global_frame:
                print(item + ': ', self.global_frame[item])

            print('Obsah lokalniho ramce:', file=sys.stderr)
            for index, item in enumerate(self.local_frame_stack):
                print(str(index) + ':', file=sys.stderr)
                for subitem in self.local_frame_stack[item]:
                    print(subitem + ': ', self.local_frame_stack[item][subitem])

            print('Obsah docasneho ramce:', file=sys.stderr)
            if self._temp_frame is not None:
                for item in self._temp_frame:
                    print(item + ': ', self._temp_frame[item])
        else:
            exit_with_error('Instrukce ma neplatny operacni kod', 32)
        self.curr_ins += 1


# Zpracovani parametru programu
if len(sys.argv) != 2:
    exit_with_error('Nepsravny format argumentu', 10)
else:
    arg = sys.argv[1].split('=', 1)
    if arg[0] == '--help':
        print(
            'Program nacte XML reprezentaci programu ze souboru a tento program interpretuje. Vstupni XML je napr.' 
            'generovan skriptem parse.php ze zdrojoveho kodu IPPcode18.\n'
            'Parametry:\n'
            '    --help         vypise na standardni vystup napovedu skriptu\n'
            '    --source=file  vstupni soubor s XML reprezentaci zdrojoveho kodu'
        )
        exit(0)
    elif arg[0] != '--source' or len(arg) < 1 or arg[1] == '':
        exit_with_error('Nepsravny format argumentu', 10)

try:
    root_elem = xml.etree.ElementTree.parse(arg[1]).getroot()
except FileNotFoundError:
    exit_with_error('Zdrojovy soubor neexistuje', 11)
except xml.etree.ElementTree.ParseError:
    exit_with_error('Zdrojovy soubor nema platny XML format', 31)

if root_elem.tag != 'program':
    exit_with_error('Korenovy element nema spravne oznaceni', 31)
if root_elem.get('language') != 'IPPcode18':
    exit_with_error('Korenovy element nema spravnou hodnotu \'language\'', 31)

interpreter = Interpreter()

for label_ins in root_elem.findall('instruction[@opcode="LABEL"]'):
    interpreter.execute(Instruction(label_ins))

max_order = len(root_elem.findall('instruction')) + 1
interpreter.curr_ins = 1

while interpreter.curr_ins != max_order:
    instr = root_elem.find('instruction[@order="' + str(interpreter.curr_ins) + '"]')
    # V pripade, ze se v souboru vyskytuje attribut order se stejnou hodnotou, nebo napriklad nejakou hodnotu
    # v posloupnosti vynecha, tak dojde k chybe
    try:
        if instr.get('opcode') == 'LABEL':
            interpreter.curr_ins += 1
            continue
        interpreter.execute(Instruction(instr))
    except AttributeError:
        exit_with_error('Instrukce v XML souboru jsou neplatne ocislovany', 31)
