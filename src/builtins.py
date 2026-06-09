"""
builtins.py — 內建函式庫

Small-C 不需要 #include，這些函式直接內建在解譯器裡：

    I/O 類    : printf、scanf、putchar、getchar、puts
    字串類    : strlen、strcpy、strcmp、strcat
    數學類    : abs、max、min、pow、sqrt、mod
    工具類    : rand、srand、memset、atoi、itoa、exit

運作方式：
    Interpreter 的 _eval_call 遇到函式呼叫時，
    先查 BUILTIN_NAMES 確認是不是內建函式，
    如果是就呼叫 BuiltinFunctions.call(name, args)，
    由這個檔案負責實際執行。
"""

import math
import random
import sys


class BuiltinError(Exception):
    """內建函式執行時的錯誤，例如 sqrt 傳入負數。"""
    pass


# ─────────────────────────────────────────────────────────────
# BUILTIN_SIGNATURES：所有內建函式的簽章
# 用途：FUNCS 指令顯示時列出這些資訊
# 格式：(回傳型別, 函式名稱, [(參數型別, 參數名稱, 是否為指標), ...])
# ─────────────────────────────────────────────────────────────

BUILTIN_SIGNATURES = [
    ('int',  'putchar',     [('int',   'ch',    False)]),
    ('int',  'getchar',     []),
    ('void', 'printf',      [('char*', 'fmt',   True), ('...', '...', False)]),
    ('void', 'puts',        [('char*', 's',     True)]),
    ('int',  'scanf',       [('char*', 'fmt',   True), ('...', '...', False)]),
    ('int',  'strlen',      [('char*', 's',     True)]),
    ('void', 'strcpy',      [('char*', 'dest',  True), ('char*', 'src', True)]),
    ('int',  'strcmp',      [('char*', 's1',    True), ('char*', 's2', True)]),
    ('void', 'strcat',      [('char*', 'dest',  True), ('char*', 'src', True)]),
    ('int',  'abs',         [('int',   'x',     False)]),
    ('int',  'max',         [('int',   'a',     False), ('int', 'b', False)]),
    ('int',  'min',         [('int',   'a',     False), ('int', 'b', False)]),
    ('int',  'pow',         [('int',   'base',  False), ('int', 'exp', False)]),
    ('int',  'sqrt',        [('int',   'x',     False)]),
    ('int',  'mod',         [('int',   'a',     False), ('int', 'b', False)]),
    ('int',  'rand',        []),
    ('void', 'srand',       [('int',   'seed',  False)]),
    ('void', 'memset',      [('char*', 'ptr',   True), ('int', 'value', False), ('int', 'size', False)]),
    ('int',  'sizeof_int',  []),
    ('int',  'sizeof_char', []),
    ('int',  'atoi',        [('char*', 's',     True)]),
    ('void', 'itoa',        [('int',   'value', False), ('char*', 'str', True)]),
    ('void', 'exit',        [('int',   'code',  False)]),
]

# 只取函式名稱組成一個集合，方便 Interpreter 快速判斷「是不是內建函式」
# set comprehension：{ sig[1] for sig in ... } 取每個 tuple 的第二個元素
BUILTIN_NAMES = {sig[1] for sig in BUILTIN_SIGNATURES}


class BuiltinFunctions:
    def __init__(self, output_cb, input_cb, memory):
        """
        output_cb : 輸出函式，printf/puts/putchar 都靠它輸出
        input_cb  : 輸入函式，scanf/getchar 靠它讀取使用者輸入
        memory    : Memory 物件，字串函式需要讀寫模擬記憶體
        """
        self._out = output_cb
        self._in  = input_cb
        self._mem = memory

    def call(self, name, args):
        """
        分派函式呼叫的總入口。
        用一個字典把名稱對應到對應的方法，
        比一長串 if-elif 更簡潔，也更容易新增函式。

        args 是已經求值完的引數整數列表，
        例如 printf("%d\n", x) 傳進來的 args 是
        [格式字串的記憶體位址, x 的整數值]。
        """
        dispatch = {
            'putchar':    self._putchar,
            'getchar':    self._getchar,
            'printf':     self._printf,
            'puts':       self._puts,
            'scanf':      self._scanf,
            'strlen':     self._strlen,
            'strcpy':     self._strcpy,
            'strcmp':     self._strcmp,
            'strcat':     self._strcat,
            'abs':        self._abs,
            'max':        self._max,
            'min':        self._min,
            'pow':        self._pow,
            'sqrt':       self._sqrt,
            'mod':        self._mod,
            'rand':       self._rand,
            'srand':      self._srand,
            'memset':     self._memset,
            'sizeof_int': self._sizeof_int,
            'sizeof_char':self._sizeof_char,
            'atoi':       self._atoi,
            'itoa':       self._itoa,
            'exit':       self._exit,
        }
        if name not in dispatch:
            raise BuiltinError(f"Unknown built-in function: {name}")
        return dispatch[name](args)

    # ─────────────────────────────────────────────────────────
    # I/O 函式
    # ─────────────────────────────────────────────────────────

    def _putchar(self, args):
        """
        輸出單一字元。
        args[0] & 0xFF 取低 8 位元，確保只處理 0～255 範圍的字元。
        回傳輸出的字元的 ASCII 值。
        """
        ch = args[0] & 0xFF
        self._out(chr(ch))
        return ch

    def _getchar(self, args):
        """
        讀取一個字元，回傳其 ASCII 值。
        讀到空輸入或 EOF 時回傳 -1（對應 C 語言的 EOF）。
        """
        line = self._in()
        if line is None or line == '':
            return -1
        return ord(line[0])

    def _printf(self, args):
        """
        格式化輸出。
        args[0] 是格式字串的記憶體位址，
        args[1:] 是後續的引數值。

        先從記憶體讀出格式字串，
        再交給 _format_string 做格式化，
        最後透過 output_cb 輸出。
        """
        if not args:
            raise BuiltinError("printf requires at least one argument")
        fmt_addr = args[0]
        fmt      = self._mem.read_string(fmt_addr)  # 從記憶體讀出格式字串
        extra    = args[1:]                          # 後續引數
        result   = self._format_string(fmt, extra)
        self._out(result)
        return 0

    def _puts(self, args):
        """
        輸出字串並自動換行。
        比 printf 簡單，不支援格式符。
        """
        addr = args[0]
        s = self._mem.read_string(addr)
        self._out(s + '\n')
        return 0

    def _scanf(self, args):
        """
        讀取使用者輸入，解析後寫入指標指向的位址。
        args[0] 是格式字串位址，args[1:] 是要寫入的各個指標位址。
        回傳成功讀取的項目數。

        例如 scanf("%d %d", &a, &b)：
            args = [格式字串位址, a 的位址, b 的位址]
            讀入 "10 20"，把 10 寫入 a 的位址，20 寫入 b 的位址
            回傳 2
        """
        if len(args) < 2:
            raise BuiltinError("scanf requires at least 2 arguments")
        fmt      = self._mem.read_string(args[0])
        ptr_args = args[1:]
        line     = self._in()
        if line is None:
            return -1
        tokens  = line.split()   # 把輸入按空白切開
        count   = 0
        tok_idx = 0
        i = 0
        while i < len(fmt):
            if fmt[i] == '%' and i + 1 < len(fmt):
                spec = fmt[i+1]
                if spec == 'd':   # 讀整數
                    if tok_idx >= len(tokens) or tok_idx >= len(ptr_args):
                        break
                    try:
                        val = int(tokens[tok_idx])
                    except ValueError:
                        break
                    self._mem.write(ptr_args[tok_idx], val)
                    tok_idx += 1
                    count   += 1
                elif spec == 'c':   # 讀字元
                    if tok_idx >= len(ptr_args):
                        break
                    ch_val = ord(tokens[tok_idx][0]) if tok_idx < len(tokens) else 0
                    self._mem.write(ptr_args[tok_idx], ch_val)
                    tok_idx += 1
                    count   += 1
                i += 2
            else:
                i += 1
        return count

    # ─────────────────────────────────────────────────────────
    # 字串函式
    # 這些函式的引數都是記憶體位址（指標），
    # 需要透過 Memory 物件讀寫實際內容
    # ─────────────────────────────────────────────────────────

    def _strlen(self, args):
        """回傳字串長度（不含結尾的 \0）。"""
        return len(self._mem.read_string(args[0]))

    def _strcpy(self, args):
        """
        把 src 字串複製到 dest。
        先從 src 位址讀出字串，再寫入 dest 位址。
        回傳 dest 位址（C 語言慣例）。
        """
        dest, src = args[0], args[1]
        s = self._mem.read_string(src)
        self._mem.write_string(dest, s)
        return dest

    def _strcmp(self, args):
        """
        比較兩個字串。
        s1 < s2 → 回傳 -1
        s1 > s2 → 回傳  1
        s1 == s2 → 回傳 0
        Python 字串的 < > 比較是按字母順序，符合 C 語言的行為。
        """
        s1 = self._mem.read_string(args[0])
        s2 = self._mem.read_string(args[1])
        if s1 < s2: return -1
        if s1 > s2: return  1
        return 0

    def _strcat(self, args):
        """
        把 src 字串接在 dest 字串後面。
        先讀出兩個字串，串接後寫回 dest 位址。
        """
        dest, src = args[0], args[1]
        s1 = self._mem.read_string(dest)
        s2 = self._mem.read_string(src)
        self._mem.write_string(dest, s1 + s2)
        return dest

    # ─────────────────────────────────────────────────────────
    # 數學函式
    # 直接用 Python 內建功能實作，很簡單
    # ─────────────────────────────────────────────────────────

    def _abs(self, args):
        return abs(args[0])

    def _max(self, args):
        return max(args[0], args[1])

    def _min(self, args):
        return min(args[0], args[1])

    def _pow(self, args):
        """
        整數次方。
        負指數回傳 0（整數不支援小數結果）。
        Python 的 ** 運算子直接支援整數次方。
        """
        base, exp = args[0], args[1]
        if exp < 0: return 0
        if exp == 0: return 1
        return base ** exp

    def _sqrt(self, args):
        """
        整數平方根（無條件捨去）。
        math.isqrt 是 Python 3.8+ 提供的整數平方根函式，
        比 int(math.sqrt(...)) 更精確，不會有浮點數誤差。
        """
        x = args[0]
        if x < 0:
            raise BuiltinError("sqrt() argument must be non-negative")
        return int(math.isqrt(x))

    def _mod(self, args):
        a, b = args[0], args[1]
        if b == 0:
            raise BuiltinError("mod() division by zero")
        return a % b

    def _rand(self, args):
        """回傳 0～32767 的隨機整數（對應 C 語言 RAND_MAX）。"""
        return random.randint(0, 32767)

    def _srand(self, args):
        """設定亂數種子，讓 rand() 的結果可重現。"""
        random.seed(args[0])
        return 0

    # ─────────────────────────────────────────────────────────
    # 工具函式
    # ─────────────────────────────────────────────────────────

    def _memset(self, args):
        """
        把從 ptr 開始的 size 格記憶體都設為 value。
        value & 0xFF 取低 8 位元，確保只寫入一個 byte。
        常用於把陣列清零：memset(arr, 0, SIZE)
        """
        ptr, value, size = args[0], args[1], args[2]
        for i in range(size):
            self._mem.write(ptr + i, value & 0xFF)
        return 0

    def _sizeof_int(self, args):
        return 4   # C 語言 int 通常是 4 bytes

    def _sizeof_char(self, args):
        return 1   # C 語言 char 永遠是 1 byte

    def _atoi(self, args):
        """
        把字串轉成整數。
        例如："2026" → 2026，"-42" → -42，"3abc" → 3（只讀數字部分）
        無法轉換時回傳 0。

        手動實作而不用 int(s) 是為了模擬 C 語言 atoi 的行為：
        只讀字串開頭的連續數字，遇到非數字就停止。
        """
        s = self._mem.read_string(args[0])
        try:
            s = s.strip()
            if not s:
                return 0
            sign = 1
            i = 0
            if s[0] in '+-':
                if s[0] == '-':
                    sign = -1
                i += 1
            num = 0
            while i < len(s) and s[i].isdigit():
                num = num * 10 + int(s[i])
                i += 1
            return sign * num
        except Exception:
            return 0

    def _itoa(self, args):
        """
        把整數轉成字串，寫入指定的記憶體位址。
        例如：itoa(12345, buf) → buf 裡會有 "12345\0"
        """
        value, str_addr = args[0], args[1]
        s = str(value)
        self._mem.write_string(str_addr, s)
        return 0

    def _exit(self, args):
        """
        終止程式執行。
        用拋出 ExitSignal 的方式通知 Interpreter 停止，
        和 ReturnSignal 的技巧相同。
        """
        raise ExitSignal(args[0] if args else 0)

    # ─────────────────────────────────────────────────────────
    # printf 格式化（_printf 的核心邏輯）
    # ─────────────────────────────────────────────────────────

    def _format_string(self, fmt: str, args: list) -> str:
        """
        處理 printf 的格式字串，回傳最終要輸出的字串。

        支援的格式符：
            %d → 十進位整數
            %c → 字元
            %s → 字串（從記憶體位址讀出）
            %x → 十六進位整數（小寫）
            %% → 輸出一個 % 字元本身

        掃描格式字串，遇到 % 就消耗一個引數並格式化，
        其他字元直接輸出。
        """
        result  = []
        arg_idx = 0    # 當前要消耗的引數索引
        i = 0
        while i < len(fmt):
            if fmt[i] == '%' and i + 1 < len(fmt):
                spec = fmt[i+1]   # % 後面的格式符字元
                if spec == 'd':
                    val = args[arg_idx] if arg_idx < len(args) else 0
                    val = _to_signed32(val)   # 轉成有號 32 位元整數
                    result.append(str(val))
                    arg_idx += 1
                    i += 2
                elif spec == 'c':
                    val = args[arg_idx] if arg_idx < len(args) else 0
                    result.append(chr(val & 0xFF))
                    arg_idx += 1
                    i += 2
                elif spec == 's':
                    addr = args[arg_idx] if arg_idx < len(args) else 0
                    result.append(self._mem.read_string(addr))  # 從記憶體讀字串
                    arg_idx += 1
                    i += 2
                elif spec == 'x':
                    val = args[arg_idx] if arg_idx < len(args) else 0
                    val = val & 0xFFFFFFFF   # 取 32 位元無號數
                    result.append(f'{val:x}')
                    arg_idx += 1
                    i += 2
                elif spec == '%':
                    result.append('%')   # %% 輸出 %
                    i += 2
                else:
                    result.append(fmt[i])   # 不認識的格式符，直接輸出 %
                    i += 1
            elif fmt[i] == '\\':
                # 處理跳脫序列（理論上 Lexer 應該已經處理了，這裡是保險）
                if i + 1 < len(fmt):
                    esc = fmt[i+1]
                    esc_map = {
                        'n': '\n', 't': '\t', '\\': '\\',
                        '"': '"',  "'": "'",  '0':  '\0', 'r': '\r'
                    }
                    result.append(esc_map.get(esc, esc))
                    i += 2
                else:
                    result.append('\\')
                    i += 1
            else:
                result.append(fmt[i])   # 一般字元直接加入結果
                i += 1
        return ''.join(result)


# ─────────────────────────────────────────────────────────────
# 輔助函式與輔助類別
# ─────────────────────────────────────────────────────────────

def _to_signed32(val):
    """
    把一個 Python 整數轉成有號 32 位元整數。

    Python 的整數沒有位元寬度限制，可以無限大，
    但 C 語言的 int 是 32 位元，有範圍限制（-2147483648 ~ 2147483647）。

    做法：
        先用 & 0xFFFFFFFF 取低 32 位元（得到 0 ~ 4294967295）
        如果結果 >= 0x80000000（2147483648），代表最高位是 1，
        是負數，要減去 0x100000000 轉成對應的負值。

    例如：
        _to_signed32(4294967295)  →  -1
        _to_signed32(2147483648)  →  -2147483648
        _to_signed32(100)         →  100（不變）
    """
    val = int(val) & 0xFFFFFFFF
    if val >= 0x80000000:
        val -= 0x100000000
    return val


class ExitSignal(Exception):
    """
    exit() 函式呼叫時拋出，通知 Interpreter 終止程式。
    code 是結束碼，對應 C 語言的 exit(0)、exit(1) 等。
    和 ReturnSignal 的原理完全相同。
    """
    def __init__(self, code):
        self.code = code