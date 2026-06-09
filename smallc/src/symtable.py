"""
symtable.py — 符號表（Symbol Table）

符號表的工作是回答兩個問題：
    1. 「這個變數名稱叫 x，它在記憶體的哪個位址？」
    2. 「這個函式叫 gcd，它的參數和主體是什麼？」

符號表管理三種東西：
    變數（VarInfo）  → 名稱、型別、記憶體位址
    函式（FuncInfo） → 名稱、參數列表、主體 AST
    常數（defines）  → #define 定義的名稱對應整數值
"""


class SymbolError(Exception):
    """符號表相關錯誤（目前保留備用）。"""
    pass


# ─────────────────────────────────────────────────────────────
# VarInfo：記錄一個變數的完整資訊
# ─────────────────────────────────────────────────────────────

class VarInfo:
    """
    代表一個已宣告變數的所有資訊。

    name       : 變數名稱，如 'x'
    type_str   : 型別字串，'int' 或 'char'
    is_ptr     : 是否為指標（有 * 號）
    array_size : 陣列長度，純量變數為 None
    addr       : 在模擬記憶體中的起始位址

    例如 int arr[8] 宣告後：
        name       = 'arr'
        type_str   = 'int'
        is_ptr     = False
        array_size = 8
        addr       = 1000   ← Memory.alloc(8) 回傳的位址
    """
    def __init__(self, name, type_str, is_ptr=False, array_size=None, addr=None):
        self.name       = name
        self.type_str   = type_str
        self.is_ptr     = is_ptr
        self.array_size = array_size
        self.addr       = addr

    @property
    def is_array(self):
        """
        用 @property 把方法包裝成屬性，
        這樣可以寫 info.is_array 而不是 info.is_array()，
        讀起來更自然。
        """
        return self.array_size is not None

    def __repr__(self):
        """除錯用，讓 print(info) 的輸出更好讀。"""
        if self.is_array:
            return f"VarInfo({self.type_str} {self.name}[{self.array_size}] @ {self.addr})"
        ptr = '*' if self.is_ptr else ''
        return f"VarInfo({self.type_str}{ptr} {self.name} @ {self.addr})"


# ─────────────────────────────────────────────────────────────
# FuncInfo：記錄一個函式的完整資訊
# ─────────────────────────────────────────────────────────────

class FuncInfo:
    """
    代表一個已定義函式的所有資訊。

    name     : 函式名稱，如 'gcd'
    ret_type : 回傳型別，'int'、'char' 或 'void'
    params   : 參數列表，每個元素是 (型別字串, 參數名稱, 是否為指標)
               例如 [('int', 'a', False), ('int', 'b', False)]
    body     : 函式主體的 Block AST 節點
               Interpreter 執行時直接走訪這個節點
    line     : 定義在原始碼第幾行（用於 FUNCS 指令顯示）
    """
    def __init__(self, name, ret_type, params, body, line=0):
        self.name     = name
        self.ret_type = ret_type
        self.params   = params
        self.body     = body
        self.line     = line

    def __repr__(self):
        params_str = ', '.join(
            f"{t}{'*' if p else ''} {n}" for t, n, p in self.params
        )
        return f"FuncInfo({self.ret_type} {self.name}({params_str}) @ line {self.line})"


# ─────────────────────────────────────────────────────────────
# Scope：單一作用域
# ─────────────────────────────────────────────────────────────

class Scope:
    """
    一個作用域就是「一個變數可見範圍」。

    例如以下程式碼有三個作用域：
        int x = 1;          ← 全域作用域
        int main() {
            int y = 2;      ← main 的作用域
            if (x > 0) {
                int z = 3;  ← if 區塊的作用域
            }
        }

    作用域之間形成「父子關係」：
        if 區塊的父作用域 → main 的作用域
        main 的父作用域   → 全域作用域

    查找變數時，先在當前作用域找，找不到就往父作用域找，
    這就是 C 語言「內層可以看到外層變數」的原理。

    parent : 父作用域，全域作用域的 parent 是 None
    vars   : 這個作用域裡宣告的所有變數（字典）
    """
    def __init__(self, parent=None):
        self.parent = parent
        self.vars: dict[str, VarInfo] = {}

    def define(self, info: VarInfo):
        """在這個作用域裡登記一個變數。"""
        self.vars[info.name] = info

    def lookup(self, name: str):
        """
        查找變數：先找自己，找不到就遞迴往父作用域找。
        如果一路找到頂（global_scope 的 parent 是 None）還是沒有，
        就回傳 None。
        """
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.lookup(name)   # 往父作用域找
        return None

    def lookup_local(self, name: str):
        """只在當前作用域找，不往上找。"""
        return self.vars.get(name)


# ─────────────────────────────────────────────────────────────
# SymbolTable：管理所有作用域的總管
# ─────────────────────────────────────────────────────────────

class SymbolTable:
    """
    符號表的主體，管理三種資料：
        _scope_stack : 作用域堆疊，最上面是當前作用域
        functions    : 所有使用者定義函式
        defines      : 所有 #define 常數
    """
    def __init__(self):
        self.global_scope  = Scope()              # 全域作用域永遠在底部
        self._scope_stack  = [self.global_scope]  # 堆疊初始只有全域作用域
        self.functions: dict[str, FuncInfo] = {}
        self.defines:   dict[str, int]      = {}

    # ── 作用域管理 ────────────────────────────────────────────

    def push_scope(self):
        """
        建立一個新作用域，放到堆疊頂端。
        進入 { } 區塊或呼叫函式時使用。

        新作用域的 parent 設為當前的頂端作用域，
        這樣 lookup 往上找時才能正確連到外層。
        """
        new_scope = Scope(parent=self._scope_stack[-1])
        self._scope_stack.append(new_scope)

    def pop_scope(self):
        """
        銷毀頂端的作用域，回到上一層。
        離開 { } 區塊或函式回傳時使用。
        保留至少一個（全域作用域），不能把底部清掉。
        """
        if len(self._scope_stack) > 1:
            self._scope_stack.pop()

    @property
    def current_scope(self):
        """當前作用域 = 堆疊的最頂端。"""
        return self._scope_stack[-1]

    # ── 變數 ──────────────────────────────────────────────────

    def declare_var(self, info: VarInfo):
        """在當前作用域登記一個變數。"""
        self.current_scope.define(info)

    def lookup_var(self, name: str) -> VarInfo | None:
        """
        從當前作用域往上查找變數。
        這是 Interpreter 最常呼叫的函式之一。
        """
        return self.current_scope.lookup(name)

    def lookup_global_var(self, name: str) -> VarInfo | None:
        """直接查全域作用域，不考慮當前位置。"""
        return self.global_scope.vars.get(name)

    # ── 函式 ──────────────────────────────────────────────────

    def define_func(self, info: FuncInfo):
        """登記一個函式定義。函式不屬於任何作用域，存在獨立的字典裡。"""
        self.functions[info.name] = info

    def lookup_func(self, name: str) -> FuncInfo | None:
        """查找函式，找不到回傳 None。"""
        return self.functions.get(name)

    # ── #define 常數 ──────────────────────────────────────────

    def add_define(self, name: str, value: int):
        """登記一個 #define 常數，如 SIZE = 8。"""
        self.defines[name] = value

    def lookup_define(self, name: str):
        """查找 #define 常數，找不到回傳 None。"""
        return self.defines.get(name)

    # ── 重置 ──────────────────────────────────────────────────

    def reset(self):
        """
        清除所有狀態，回到初始。
        NEW 指令和每次 RUN 前都會呼叫。
        """
        self.global_scope  = Scope()
        self._scope_stack  = [self.global_scope]
        self.functions.clear()
        self.defines.clear()