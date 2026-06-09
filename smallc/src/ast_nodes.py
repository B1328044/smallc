"""
ast_nodes.py
定義抽象語法樹節點的資料結構。
不會有執行動作，只是定義資料的形狀。
Parser根據此形狀將積木拼起來，Interpreter負責讀懂拼好的樣子來執行。

抽象語法樹：
Parser讀完Token,把程式結構轉為一棵樹
ex. int x = 4 + 3
into => VarDecl
        |--type_sta = "int"
        |--name     = "x"
        |--init = BinOp
                  |--op    = "+"
                  |--left  = IntLit(4)
                  |--right = IntLit(3)

"""

class Node:
    """所有節點皆屬於共同基底類別"""
    pass

class Program(Node):
    """整支程式的根節點，decls=一個list，放所有最外層的宣告，如#define"""
    def __init__(self, decls):
        self.decls = decls

class FuncDef(Node):
    """
    定義節點
    rec_type=回傳型別字串
    name=函式名稱字串
    params=參數列表，（型別字串，參數名稱，是否為指標）
    body=Block節點（函式主體）
    line=節點在原始碼第幾行（錯誤訊息用）
    """
    def __init__(self, ret_type, name, params, body, line=0):
        self.ret_type = ret_type
        self.name = name
        self.params = params
        self.body = body
        self.line = line

class VarDecl(Node):
    """
    變數宣告節點，
    type_str='int'or'char'
    name=變數名稱
    is_ptr=是否為指標變數(*有無)
    array_size=若是陣列，放陣列長度。純量則none
    init=初始值的運算是節點，沒有就none
    line=原始碼行號
    """

    def __init__(self, type_str, name, is_ptr=False, array_size=None, init=None, line=0):
        self.type_str = type_str
        self.name = name
        self.is_ptr = is_ptr
        self.array_size = array_size
        self.init = init
        self.line = line

class DefineDirective(Node):
    """
    #define前置處理器指令節點
    name=常數名稱字串
    value=常數值
    line=原始碼行號
    """
    def __init__(self, name, value, line=0):
        self.name = name
        self.value = value
        self.line = line

"""
陳述句類節點，包含函式主體的每一條執行單位
"""

class Block(Node):
    """
    {...}大括號區塊

    stmts=裡面的陳述句list，依序執行
    """
    def __init__(self, stmts, line=0):
        self.stmts = stmts
        self.line = line

class IfStmt(Node):
    """
    If/If-else陳述句所用

    If(cond){then_stmt}else{else_stmt}

    cond=條件運算式節點
    then_stmt=條件為真實執行的陳述句，通常是Block
    else_stmt=else分支，沒有else時是none
    """

    def __init__(self, cond, then_stmt, else_stmt=None, line=0):
        self.cond = cond
        self.then_stmt = then_stmt
        self.else_stmt = else_stmt
        self.line = line

class WhileStmt(Node):
    """
    while迴圈

    while(cond) {body}

    cond=每次迭代前檢查的條件運算式
    body=迴圈主體陳述句
    """
    def __init__(self, cond,body,line=0):
        self.cond = cond
        self.body = body
        self.line = line

class ForStmt(Node):
    """
    for迴圈

    for(init;cond;update){body}

    init=初始化
    cond=條件判斷運算式
    update=每次迭代結束後執行的運算式
    body=迴圈主體
    """

    def __init__(self, init, cond, update, body, line=0):
        self.init = init
        self.cond = cond
        self.update = update
        self.body = body
        self.line = line

class DoWhileStmt(Node):
    """
    do-while

    do{body} while{cond}

    body=先執行一次的主體
    cond=執行後判斷的條件
    """

    def __init__(self, body, cond, line=0):
        self.body = body
        self.cond = cond
        self.line = line

class ReturnStmt(Node):
    """
    return陳述句

    expr=回傳值的運算式節點
    """

    def __init__(self, expr=None, line=0):
        self.expr = expr
        self.line = line

class BreakStmt(Node):
    """
    Break陳述句
    跳出最近的一層while/for/do-while
    """
    def __init__(self, line=0):
        self.line = line

class ContinueStmt(Node):
    """
    Continue陳述句
    跳過本次迭代剩餘的程式碼，直接進入下一次迭代
    """
    def __init__(self, line=0):
        self.line = line

class ExprStmt(Node):
    """
    「運算式陳述句」一單獨一行的運算式，後面跟分號
    ex. printf("hello"); or x = 5;

    expr=運算式節點
    """

    def __init__(self, expr, line=0):
        self.expr = expr
        self.line = line

class EmptyStmt(Node):
    """
    空陳述句（只有分號）
    出現於for迴圈的空body或多餘的分號
    """
    def __init__(self, line=0):
        self.line = line

"""
運算式類節點，會產生一個值的code
"""

class IntLit(Node):
    """
    整數字面值

    value=Python int
    """
    def __init__(self, value, line=0):
        self.value = value
        self.line = line

class CharLit(Node):
    """
    字源字面值

    value=Python int(字元的ASCII碼)
    """

    def __init__(self, value, line=0):
        self.value = value #儲存的是ASCII整數，不是字元
        self.line = line

class StringLit(Node):
    """
    字串字面值

    value=Python str(跳脫序列是由Lexer處理)
    Interpreter執行時會把字串寫進模擬記憶體，並回傳起始位址
    """
    def __init__(self, value, line=0):
        self.value = value
        self.line = line

class Ident(Node):
    """
    識別字（變數名稱或#define常數名稱）

    Interpreter遇到此節點時
    會去符號表查詢名稱，讀出記憶體位址的值
    """
    def __init__(self,name,line=0):
        self.name = name
        self.line = line

class BinOp(Node):
    """
    二元運算元（兩個運算元）
    ex. a + b, x > 0, a && b

    op=運算子字串 ex.'+','-','%','>','==''||','^'
    left=左運算元節點
    right=右運算元節點
    """
    def __init__(self, op, left, right, line=0):
        self.op = op
        self.right = right
        self.left = left
        self.line = line

class UnaryOp(Node):
    """
    一元運算元
    ex. -x, !flag, *ptr

    op: '-' = 負號
        '!'邏輯非
        '~'位元補數
        '&'取址
        '*'取值
        '++'前置遞增
        '--'前置遞減
    operand=被操作的運算式節點
    """
    def __init__(self, op, operand, line=0):
        self.op = op
        self.operand = operand
        self.line = line

class Assign(Node):
    """
    指定運算式（賦值）

    op=指定運算子'='或複合指定'+=','-=','*='...
    target=被賦值的對象
    value=右側運算式節點

    複合指定的展開方式：
       x += 3 就是 x = x + 3
       但Interpreter直接在Assign節點中處理，不需要展開成兩個節點
    """

    def __init__(self, op, target, value, line=0):
        self.op = op
        self.target = target
        self.value = value
        self.line = line


class ArrayIndex(Node):
    """
    陣列索引運算式
    ex. arr[i] or data[0]

    array=被索引的運算式
    index=索引運算式節點

    Interpreter計算時
    先取出array的值（記憶體起始位置）
    加上index的值，得到目標格子的位址
    再從記憶體讀出該位址的值
    """
    def __init__(self, array, index, line=0):
        self.array =array
        self.index = index
        self.line = line

class FuncCall(Node):

    """
    函式呼叫運算式
    name=函式名稱字串
    args=引數運算式節點的list（依序對應參數）

    Interpreter遇到這個節點時
    1.先逐一求值每個引數
    2.查負號表，找函式定義
    3.建立新的作用域，把引數值綁定到參數名稱
    4.執行函式主體
    5.回傳return 的值
    """

    def __init__(self, name, args, line=0):
        self.name = name
        self.args = args
        self.line = line

class SwitchStmt(Node):
    """
    switch 陳述句

    switch (expr) {
        case 1: ...
        case 2: ...
        default: ...
    }

    expr  : 要比對的運算式
    cases : list of (值, [陳述句list]) ← 每個 case
    default_stmts : default 區塊的陳述句list，沒有就是 None
    """
    def __init__(self, expr, cases, default_stmts=None, line=0):
        self.expr          = expr
        self.cases         = cases          # [(int值, [stmt,...]), ...]
        self.default_stmts = default_stmts  # [stmt,...] or None
        self.line          = line