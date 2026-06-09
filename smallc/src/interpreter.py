"""
interpreter.py — 樹狀走訪直譯器（Tree-Walking Interpreter）

直譯器的工作是「走訪 AST，實際執行每個節點代表的動作」。

運作方式：
    _exec_stmt  負責執行「陳述句」節點（不產生值）
    _eval       負責計算「運算式」節點（產生一個整數值）
    兩個函式互相呼叫，一層一層走完整棵 AST。

例如執行 if (x > 0) { printf("%d\n", x); }：
    _exec_stmt(IfStmt)
        → _eval(BinOp('>', Ident('x'), IntLit(0)))  ← 計算條件
            → _eval(Ident('x'))  → 去記憶體讀 x 的值
            → _eval(IntLit(0))   → 直接回傳 0
            → 回傳 1（x > 0 為真）
        → 條件為真，_exec_stmt(Block)
            → _exec_stmt(ExprStmt)
                → _eval(FuncCall('printf', [...]))
                    → 呼叫內建函式 printf，輸出結果
"""

from .ast_nodes import (
    Program, FuncDef, VarDecl, DefineDirective,
    Block, IfStmt, WhileStmt, ForStmt, DoWhileStmt,
    ReturnStmt, BreakStmt, ContinueStmt, ExprStmt, EmptyStmt,
    IntLit, CharLit, StringLit, Ident,
    BinOp, UnaryOp, Assign, ArrayIndex, FuncCall, SwitchStmt
)
from .symtable import SymbolTable, VarInfo, FuncInfo
from .memory import Memory
from .builtins import BuiltinFunctions, BuiltinError, ExitSignal, BUILTIN_NAMES, _to_signed32
from .lexer import tokenize, LexerError
from .parser import Parser, ParseError


# ─────────────────────────────────────────────────────────────
# 控制流程用的特殊 Exception
#
# Python 的 Exception 機制在這裡被當作「訊號」使用，
# 而不是真正的「錯誤」。
# 這是實作直譯器的常見技巧：
#   當執行到 return/break/continue 時，
#   用拋出 Exception 的方式「跳出」當前的執行框架，
#   由上層的 try/except 捕捉並處理。
# ─────────────────────────────────────────────────────────────

class RuntimeError_(Exception):
    """
    執行期錯誤，例如：
        - 除以零
        - 陣列索引越界
        - 使用未定義的變數
    名稱加底線是為了避開 Python 內建的 RuntimeError。
    """
    def __init__(self, msg, line=0):
        super().__init__(msg)
        self.line = line


class ReturnSignal(Exception):
    """
    執行到 return 陳述句時拋出。
    value 是回傳值（可以是 None，代表 void 函式）。
    由 _call_func 捕捉，把值傳回給呼叫者。
    """
    def __init__(self, value):
        self.value = value


class BreakSignal(Exception):
    """
    執行到 break 時拋出。
    由 while/for/do-while 的迴圈執行程式碼捕捉，
    用來跳出迴圈。
    """
    pass


class ContinueSignal(Exception):
    """
    執行到 continue 時拋出。
    由迴圈執行程式碼捕捉，
    用來跳過本次迭代剩下的程式碼。
    """
    pass


class Interpreter:
    def __init__(self, output_cb=None, input_cb=None, trace_cb=None):
        """
        output_cb : 輸出回呼函式，預設是 print。
                    REPL 會傳入自己的輸出函式，讓輸出導向正確的地方。
        input_cb  : 輸入回呼函式，預設是 input()。
        trace_cb  : TRACE ON 模式下，每執行一行就呼叫這個函式。
        """
        self._output_cb = output_cb or (lambda s: print(s, end='', flush=True))
        self._input_cb  = input_cb  or (lambda: input())
        self._trace_cb  = trace_cb
        self.trace_mode = False

        self.symtable = SymbolTable()   # 符號表：管理變數與函式的定義
        self.memory   = Memory()        # 模擬記憶體：存放變數的實際值
        self.builtins = BuiltinFunctions(self._output_cb, self._input_cb, self.memory)

        # 記錄全域變數的宣告順序，VARS 指令依照這個順序顯示
        self._global_var_order: list[str] = []

    def reset(self):
        """
        清除所有執行狀態。
        RUN 之前和 NEW 指令後都會呼叫。
        """
        self.symtable.reset()
        self.memory.reset()
        self.builtins = BuiltinFunctions(self._output_cb, self._input_cb, self.memory)
        self._global_var_order.clear()

    # ─────────────────────────────────────────────────────────
    # 程式執行（RUN 指令用）
    # ─────────────────────────────────────────────────────────

    def execute_program(self, program: Program):
        """
        執行一整支程式（緩衝區裡的完整程式碼）。

        兩個階段：
        1. 第一遍：掃描所有最外層宣告，
                   把 #define、函式定義、全域變數都登記好。
        2. 第二遍：找到 main() 並執行它。

        為什麼要兩遍？
            因為 C 語言允許先呼叫後定義：
            main() 裡呼叫 foo()，但 foo() 定義在 main() 後面。
            第一遍先把所有函式都登記完，
            第二遍執行時就能找到了。
        """
        # 重置記憶體和全域變數，但保留函式定義（由第一遍重新登記）
        self.memory.reset()
        self.builtins = BuiltinFunctions(self._output_cb, self._input_cb, self.memory)
        self.symtable.global_scope.vars.clear()
        self._global_var_order.clear()

        # 第一遍：登記所有宣告
        for decl in program.decls:
            self._process_top_level_decl(decl)

        # 找 main() 並執行
        main_func = self.symtable.lookup_func('main')
        if not main_func:
            raise RuntimeError_("No main() function defined")

        try:
            ret = self._call_func(main_func, [])
        except ExitSignal as e:
            return e.code          # exit() 函式被呼叫
        except ReturnSignal as r:
            ret = r.value
        return ret if ret is not None else 0

    def _process_top_level_decl(self, decl):
        """
        處理一個最外層宣告（第一遍用）。
        DefineDirective → 登記到符號表的 defines 字典
        FuncDef         → 登記到符號表的 functions 字典
        VarDecl         → 配置記憶體並登記到全域作用域
        """
        if isinstance(decl, DefineDirective):
            self.symtable.add_define(decl.name, decl.value)
        elif isinstance(decl, FuncDef):
            info = FuncInfo(decl.name, decl.ret_type, decl.params, decl.body, decl.line)
            self.symtable.define_func(info)
        elif isinstance(decl, VarDecl):
            self._declare_var(decl, global_scope=True)

    # ─────────────────────────────────────────────────────────
    # 互動模式執行（在 sc> 提示符下直接輸入程式碼用）
    # ─────────────────────────────────────────────────────────

    def exec_interactive(self, stmt_or_decl):
        """
        在互動模式下執行單一陳述句或宣告。
        和 execute_program 的差別是：
            不需要 main()，每行輸入立刻執行。
            全域狀態（變數、函式）在整個互動會話中持續累積。
        """
        if isinstance(stmt_or_decl, DefineDirective):
            self.symtable.add_define(stmt_or_decl.name, stmt_or_decl.value)
        elif isinstance(stmt_or_decl, FuncDef):
            info = FuncInfo(stmt_or_decl.name, stmt_or_decl.ret_type,
                            stmt_or_decl.params, stmt_or_decl.body, stmt_or_decl.line)
            self.symtable.define_func(info)
        elif isinstance(stmt_or_decl, VarDecl):
            self._declare_var(stmt_or_decl, global_scope=True)
        else:
            self._exec_stmt(stmt_or_decl)   # 一般陳述句直接執行

    # ─────────────────────────────────────────────────────────
    # 變數配置
    # ─────────────────────────────────────────────────────────

    def _declare_var(self, decl: VarDecl, global_scope=False):
        """
        為一個變數宣告配置記憶體，並登記到符號表。

        純量變數：配置 1 格記憶體
        陣列變數：配置 array_size 格連續記憶體

        array_size 可能是整數，也可能是 Ident 節點（來自 #define 常數），
        後者需要先查符號表解析出實際數字。
        """
        size     = 1
        arr_size = None

        if decl.array_size is not None:
            if isinstance(decl.array_size, int):
                arr_size = decl.array_size
            else:
                # array_size 是 Ident 節點，代表用了 #define 常數當陣列大小
                # 例如：int data[SIZE]，SIZE 是 #define SIZE 8
                resolved = self.symtable.lookup_define(decl.array_size.name)
                if resolved is None:
                    raise RuntimeError_(
                        f"Undefined array size constant: '{decl.array_size.name}'",
                        decl.line
                    )
                arr_size = resolved
            size = arr_size   # 陣列要配置多格

        addr = self.memory.alloc(size)   # 在模擬記憶體裡配置空間，取得起始位址
        info = VarInfo(decl.name, decl.type_str, decl.is_ptr, arr_size, addr)

        if global_scope:
            self.symtable.global_scope.define(info)
            if decl.name not in self._global_var_order:
                self._global_var_order.append(decl.name)  # 記錄宣告順序
        else:
            self.symtable.current_scope.define(info)  # 登記到當前作用域

        # 處理初始值
        if decl.init is not None:
            val = self._eval(decl.init)
            if isinstance(val, str):
                self.memory.write_string(addr, val)   # 字串初始值
            else:
                self.memory.write(addr, val)          # 數值初始值
        elif decl.is_ptr and decl.array_size is None:
            self.memory.write(addr, 0)                # 指標預設為 NULL（0）

    # ─────────────────────────────────────────────────────────
    # 陳述句執行
    # ─────────────────────────────────────────────────────────

    def _exec_stmt(self, stmt, source_lines=None):
        """
        執行一個陳述句節點。
        這個函式是一個大型的 if-elif 分派器，
        根據節點的型別決定要做什麼。
        """
        if stmt is None or isinstance(stmt, EmptyStmt):
            return   # 空陳述句，什麼都不做

        # TRACE 模式：執行前先顯示行號和內容
        if self.trace_mode and self._trace_cb and stmt.line:
            self._trace_cb(stmt.line, stmt)

        if isinstance(stmt, Block):
            # 大括號區塊：建立新作用域，依序執行每個陳述句，結束後銷毀作用域
            # push_scope/pop_scope 確保區域變數在區塊結束後就消失
            self.symtable.push_scope()
            try:
                for s in stmt.stmts:
                    self._exec_stmt(s, source_lines)
            finally:
                self.symtable.pop_scope()   # 就算中途拋出例外，作用域也一定會被清除

        elif isinstance(stmt, VarDecl):
            self._declare_var(stmt)   # 宣告區域變數

        elif isinstance(stmt, ExprStmt):
            if stmt.expr is not None:
                self._eval(stmt.expr)   # 計算運算式（結果通常被丟棄，但副作用留下）
                                        # 例如 printf(...)、x = 5 的副作用是輸出/改值

        elif isinstance(stmt, IfStmt):
            cond_val = self._eval(stmt.cond)   # 計算條件
            if cond_val:
                self._exec_stmt(stmt.then_stmt, source_lines)
            elif stmt.else_stmt:
                self._exec_stmt(stmt.else_stmt, source_lines)

        elif isinstance(stmt, WhileStmt):
            while self._eval(stmt.cond):   # 每次迭代前重新計算條件
                try:
                    self._exec_stmt(stmt.body, source_lines)
                except BreakSignal:
                    break      # break 陳述句拋出的訊號，跳出迴圈
                except ContinueSignal:
                    continue   # continue 陳述句拋出的訊號，跳到下一次迭代

        elif isinstance(stmt, ForStmt):
            if stmt.init is not None:
                if isinstance(stmt.init, VarDecl):
                    # for (int i = 0; ...) 這種寫法
                    # 變數 i 的作用域只在 for 迴圈內，所以要建立新作用域
                    self.symtable.push_scope()
                    try:
                        self._declare_var(stmt.init)
                        while stmt.cond is None or self._eval(stmt.cond):
                            try:
                                self._exec_stmt(stmt.body, source_lines)
                            except BreakSignal:
                                return
                            except ContinueSignal:
                                pass
                            if stmt.update:
                                self._eval(stmt.update)
                    finally:
                        self.symtable.pop_scope()
                    return
                else:
                    self._eval(stmt.init)   # 一般運算式初始化，如 i = 0

            while stmt.cond is None or self._eval(stmt.cond):
                try:
                    self._exec_stmt(stmt.body, source_lines)
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                if stmt.update:
                    self._eval(stmt.update)   # 每次迭代結束執行更新，如 i = i + 1

        elif isinstance(stmt, DoWhileStmt):
            while True:
                try:
                    self._exec_stmt(stmt.body, source_lines)   # 先執行一次
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                if not self._eval(stmt.cond):   # 再判斷條件，為假才停
                    break

        elif isinstance(stmt, ReturnStmt):
            val = self._eval(stmt.expr) if stmt.expr else None
            raise ReturnSignal(val)   # 用拋出例外的方式把值傳回給呼叫者

        elif isinstance(stmt, BreakStmt):
            raise BreakSignal()       # 向上拋，由最近的迴圈捕捉

        elif isinstance(stmt, ContinueStmt):
            raise ContinueSignal()    # 向上拋，由最近的迴圈捕捉

        elif isinstance(stmt, DefineDirective):
            self.symtable.add_define(stmt.name, stmt.value)
        elif isinstance(stmt, SwitchStmt):
            """
            執行 switch 陳述句
            步驟：
            1.計算expr的值 
            2.依序比對每個case的值
            3.找到匹配的值就執行其陳述句
            4.沒有匹配就執行default
            5.支援break跳出switch
            """
            val = self._eval(stmt.expr)
            matched = False

            try:
                for case_val, case_stmts in stmt.cases:
                    if val == case_val:
                        matched = True
                        for s in case_stmts:
                            self._exec_stmt(s, source_lines)
                        break

                if not matched and stmt.default_stmts is not None:
                    for s in stmt.default_stmts:
                        self._exec_stmt(s, source_lines)
                
            except BreakSignal:
                pass
    # ─────────────────────────────────────────────────────────
    # 運算式求值
    # ─────────────────────────────────────────────────────────

    def _eval(self, node):
        """
        計算一個運算式節點，回傳一個整數值。
        這是直譯器的核心，幾乎每一種運算式都在這裡處理。
        """
        if node is None:
            return 0

        if isinstance(node, IntLit):
            return node.value    # 直接回傳整數值

        if isinstance(node, CharLit):
            return node.value    # 字元存的是 ASCII 整數，直接回傳

        if isinstance(node, StringLit):
            # 字串字面值：在記憶體配置空間，寫入字串內容，回傳起始位址
            # 這個位址之後會被 printf 的 %s 格式符讀取
            addr = self.memory.alloc(len(node.value) + 1)  # +1 是 C 字串結尾的 \0
            self.memory.write_string(addr, node.value)
            return addr

        if isinstance(node, Ident):
            name = node.name
            # 先查 #define 常數（如 SIZE），找到就直接回傳值
            dval = self.symtable.lookup_define(name)
            if dval is not None:
                return dval
            # 再查變數
            info = self.symtable.lookup_var(name)
            if info is None:
                raise RuntimeError_(f"Undefined variable: '{name}'", node.line)
            if info.is_array:
                return info.addr   # 陣列名稱的值是起始位址（C 語言的陣列退化規則）
            return self.memory.read(info.addr)   # 純量變數：讀出記憶體中的值

        if isinstance(node, ArrayIndex):
            arr_val = self._eval(node.array)   # 取得陣列起始位址
            idx     = self._eval(node.index)   # 計算索引值
            # 邊界檢查（只有能查到陣列大小時才做）
            if isinstance(node.array, Ident):
                info = self.symtable.lookup_var(node.array.name)
                if info and info.is_array and (idx < 0 or idx >= info.array_size):
                    raise RuntimeError_(
                        f"Array index out of bounds (index {idx}, size {info.array_size})",
                        node.line
                    )
            return self.memory.read(arr_val + idx)   # 讀取 起始位址 + 索引 的記憶體格

        if isinstance(node, UnaryOp):
            return self._eval_unary(node)

        if isinstance(node, BinOp):
            return self._eval_binop(node)

        if isinstance(node, Assign):
            return self._eval_assign(node)

        if isinstance(node, FuncCall):
            return self._eval_call(node)

        raise RuntimeError_(f"Unknown expression node: {type(node).__name__}", 0)

    def _eval_unary(self, node: UnaryOp):
        """計算一元運算式。"""
        op = node.op
        if op == '-':
            return -self._eval(node.operand)             # 數值負號
        if op == '!':
            return 1 if not self._eval(node.operand) else 0   # 邏輯非
        if op == '~':
            return ~self._eval(node.operand)             # 位元補數
        if op == '*':
            addr = self._eval(node.operand)
            if addr == 0:
                raise RuntimeError_("null pointer dereference", node.line)
            return self.memory.read(addr)                # 指標取值：讀取位址的內容
        if op == '&':
            # 取址：回傳變數在模擬記憶體中的位址
            operand = node.operand
            if isinstance(operand, Ident):
                info = self.symtable.lookup_var(operand.name)
                if info is None:
                    raise RuntimeError_(f"Cannot take address of undefined: '{operand.name}'", node.line)
                return info.addr
            if isinstance(operand, ArrayIndex):
                base = self._eval(operand.array)
                idx  = self._eval(operand.index)
                return base + idx   # 陣列元素的位址 = 起始位址 + 索引
            raise RuntimeError_("Cannot take address of non-lvalue", node.line)
        if op == '++':
            return self._modify_lval(node.operand, +1)  # 前置遞增
        if op == '--':
            return self._modify_lval(node.operand, -1)  # 前置遞減
        raise RuntimeError_(f"Unknown unary op: {op}", node.line)

    def _modify_lval(self, lval, delta):
        """
        對一個 lvalue（可被賦值的對象）做 +delta 修改。
        用於 ++ 和 -- 運算子。
        lvalue 可以是：普通變數、指標取值（*p）、陣列元素（arr[i]）
        """
        if isinstance(lval, Ident):
            info = self.symtable.lookup_var(lval.name)
            if info is None:
                raise RuntimeError_(f"Undefined variable: '{lval.name}'", lval.line)
            v = self.memory.read(info.addr) + delta
            self.memory.write(info.addr, v)
            return v
        if isinstance(lval, UnaryOp) and lval.op == '*':
            addr = self._eval(lval.operand)
            v = self.memory.read(addr) + delta
            self.memory.write(addr, v)
            return v
        if isinstance(lval, ArrayIndex):
            base = self._eval(lval.array)
            idx  = self._eval(lval.index)
            v = self.memory.read(base + idx) + delta
            self.memory.write(base + idx, v)
            return v
        raise RuntimeError_("Cannot modify non-lvalue", 0)

    def _eval_binop(self, node: BinOp):
        """
        計算二元運算式。
        && 和 || 做短路求值，其他的先把左右兩側都算完再做運算。
        """
        op = node.op

        # 短路求值：左側已能決定結果時，右側不執行
        if op == '&&':
            # 左側為假（0）→ 整體一定是假，不用算右側
            return 1 if (self._eval(node.left) and self._eval(node.right)) else 0
        if op == '||':
            lv = self._eval(node.left)
            if lv:
                return 1   # 左側為真 → 整體一定是真，不用算右側
            return 1 if self._eval(node.right) else 0

        left  = self._eval(node.left)
        right = self._eval(node.right)

        if op == '+': return left + right
        if op == '-': return left - right
        if op == '*': return left * right
        if op == '/':
            if right == 0:
                raise RuntimeError_("division by zero", node.line)
            return int(left / right)   # C 語言除法：無條件截斷（不是四捨五入）
        if op == '%':
            if right == 0:
                raise RuntimeError_("division by zero", node.line)
            return int(left - int(left/right)*right)   # C 語言取餘數
        if op == '<':  return 1 if left < right  else 0
        if op == '>':  return 1 if left > right  else 0
        if op == '<=': return 1 if left <= right else 0
        if op == '>=': return 1 if left >= right else 0
        if op == '==': return 1 if left == right else 0
        if op == '!=': return 1 if left != right else 0
        if op == '&':  return left & right   # 位元 AND
        if op == '|':  return left | right   # 位元 OR
        if op == '^':  return left ^ right   # 位元 XOR
        if op == '<<': return left << right  # 左移
        if op == '>>': return left >> right  # 右移

        raise RuntimeError_(f"Unknown binary op: {op}", node.line)

    def _eval_assign(self, node: Assign):
        """
        計算指定運算式（= += -= 等）。

        步驟：
        1. 計算右側的值（rval）
        2. 找到左側 lvalue 的記憶體位址和當前值
        3. 依照運算子計算新值
        4. 寫入記憶體
        5. 回傳新值（C 語言的指定運算式本身也有值）
        """
        rval   = self._eval(node.value)
        target = node.target

        def get_addr_and_current():
            """取得 lvalue 的記憶體位址和當前值。"""
            if isinstance(target, Ident):
                info = self.symtable.lookup_var(target.name)
                if info is None:
                    raise RuntimeError_(f"Undefined variable: '{target.name}'", node.line)
                return info.addr, self.memory.read(info.addr)
            if isinstance(target, UnaryOp) and target.op == '*':
                addr = self._eval(target.operand)    # *p = ... 先算出指標值（位址）
                return addr, self.memory.read(addr)
            if isinstance(target, ArrayIndex):
                base = self._eval(target.array)
                idx  = self._eval(target.index)
                # 邊界檢查
                if isinstance(target.array, Ident):
                    info = self.symtable.lookup_var(target.array.name)
                    if info and info.is_array and (idx < 0 or idx >= info.array_size):
                        raise RuntimeError_(
                            f"Array index out of bounds (index {idx}, size {info.array_size})",
                            node.line
                        )
                return base + idx, self.memory.read(base + idx)
            raise RuntimeError_("Cannot assign to non-lvalue", node.line)

        addr, cur = get_addr_and_current()

        # 根據運算子計算新值
        if   node.op == '=':  new_val = rval
        elif node.op == '+=': new_val = cur + rval
        elif node.op == '-=': new_val = cur - rval
        elif node.op == '*=': new_val = cur * rval
        elif node.op == '/=':
            if rval == 0: raise RuntimeError_("division by zero", node.line)
            new_val = int(cur / rval)
        elif node.op == '%=':
            if rval == 0: raise RuntimeError_("division by zero", node.line)
            new_val = int(cur - int(cur/rval)*rval)
        else:
            raise RuntimeError_(f"Unknown assignment op: {node.op}", node.line)

        self.memory.write(addr, new_val)
        return new_val

    def _eval_call(self, node: FuncCall):
        """
        執行函式呼叫。
        先判斷是內建函式（printf、sqrt 等）還是使用者定義函式。
        """
        name = node.name
        args = [self._eval(a) for a in node.args]   # 先把所有引數都算好

        if name in BUILTIN_NAMES:
            try:
                return self.builtins.call(name, args)   # 委託給 builtins 模組處理
            except BuiltinError as e:
                raise RuntimeError_(str(e), node.line)

        func = self.symtable.lookup_func(name)
        if func is None:
            raise RuntimeError_(f"Undefined function: '{name}'", node.line)

        try:
            result = self._call_func(func, args)
        except ReturnSignal as r:
            result = r.value
        return result if result is not None else 0

    def _call_func(self, func: FuncInfo, args: list):
        """
        實際執行一個使用者定義函式。

        步驟：
        1. 建立新作用域（函式有自己的區域變數空間）
        2. 把引數值一一綁定到參數名稱
        3. 執行函式主體的每一條陳述句
        4. 捕捉 ReturnSignal 取得回傳值
        5. 銷毀作用域（函式結束，區域變數消失）
        """
        self.symtable.push_scope()
        try:
            # 綁定參數：每個參數在記憶體裡配置一格，寫入對應的引數值
            for i, (ptype, pname, pis_ptr) in enumerate(func.params):
                val  = args[i] if i < len(args) else 0
                addr = self.memory.alloc(1)
                self.memory.write(addr, val)
                info = VarInfo(pname, ptype, pis_ptr, None, addr)
                self.symtable.current_scope.define(info)

            # 執行函式主體
            for stmt in func.body.stmts:
                self._exec_stmt(stmt)

        except ReturnSignal as r:
            return r.value   # 捕捉 return，取出回傳值
        finally:
            self.symtable.pop_scope()   # 一定會執行，確保作用域被清除
        return None   # 函式執行完沒有 return，回傳 None（void）

    # ─────────────────────────────────────────────────────────
    # VARS 指令顯示用
    # ─────────────────────────────────────────────────────────

    def get_vars_display(self) -> list[str]:
        """回傳所有全域變數的顯示字串，供 VARS 指令使用。"""
        lines = []
        for name in self._global_var_order:
            info = self.symtable.global_scope.vars.get(name)
            if info is None:
                continue
            lines.append(self._format_var(info))
        return lines

    def _format_var(self, info: VarInfo) -> str:
        """把一個變數的資訊格式化成易讀的字串。"""
        if info.is_array:
            # 陣列：顯示前幾個元素
            vals = []
            for i in range(min(info.array_size, 10)):  # 最多顯示 10 個
                try:
                    vals.append(str(self.memory.read(info.addr + i)))
                except Exception:
                    vals.append('?')
            arr_str = '{' + ', '.join(vals)
            if info.array_size > 10:
                arr_str += ', ...'   # 超過 10 個就用 ... 省略
            arr_str += '}'
            return f"  {info.type_str} {info.name}[{info.array_size}] = {arr_str}"
        elif info.is_ptr:
            try:
                ptr_val = self.memory.read(info.addr)
                return f"  {info.type_str}* {info.name} = {ptr_val}"
            except Exception:
                return f"  {info.type_str}* {info.name} = ?"
        else:
            try:
                val = self.memory.read(info.addr)
                if info.type_str == 'char':
                    if 32 <= val <= 126:   # 可列印字元範圍
                        return f"  char {info.name} = {val} ('{chr(val)}')"
                    return f"  char {info.name} = {val}"
                return f"  int {info.name} = {val}"
            except Exception:
                return f"  {info.type_str} {info.name} = ?"
