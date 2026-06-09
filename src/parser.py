"""
parser.py語法分析器
Parser的工作室把Lexer產出的Token串列，照著文法規則組裝成AST

用遞迴下降解析 => 每一種語法結構都對應一個函式，函式互相呼叫，如文法規則互相參照

ex._parse_statemant遇到if呼叫 _parse_if
   需要解析條件，所以呼叫_parse_assign_expr
   _parse_assign_expr往下呼叫_parse_or
   再接下去呼叫_parse_and，一層層往下，直到最基本的數字或識別字
"""

from .lexer import TokenType as TT, Token #TT是縮寫
from .ast_nodes import (
    Program, FuncDef, VarDecl, DefineDirective,
    Block, IfStmt, WhileStmt, ForStmt, DoWhileStmt,
    ReturnStmt, BreakStmt, ContinueStmt, ExprStmt, EmptyStmt,
    IntLit, CharLit, StringLit, Ident,
    BinOp, UnaryOp, Assign, ArrayIndex, FuncCall, SwitchStmt
)

class ParseError(Exception):
    """
    語法分析階段的錯誤。ex.缺少分號、括號不匹配、關鍵字用錯地方，
    都利用line的紀錄去顯示錯誤位置
    """
    def __init__(self, msg, line=0):
        super().__init__(msg)
        self.line = line

class Parser:

    def __init__(self, tokens):
        self.tokens = tokens #lexer產出的Token
        self.pos = 0 #當前游標，只向下一個要讀的Token

    #輔助方法，共四種，識Parser的基礎操作，幾乎每個解析函式都用到
    def peek(self, offset=0):
        """
        回傳當前位置加上offset的Token，但不移動游標。
        offset = 0 => 看當前的 Token
        offset = 1 => 往後多看一個（用來預判）

        如果超過範圍會回傳最後一個Token（EOF），就不用另外檢查越界
        """
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1] #安全回傳EOF
    
    def advance(self):
        """
        「消耗」當前的Token
        回傳，然後游標往後移一格。若到最後就不再移動（停在EOF）
        """
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok
    def check(self, *types):
        """
        確認目前的Token是否符合種類，回傳True/False，不移動游標
        可回傳多個種類，self.check(TT.INT, TT.CHAR) => 只要是INT或CHAR就回傳True
        """
        return self.peek().type in types
    
    def match(self, *types):
        """
        「嘗試消耗」
        如果當前的Token符合，就消耗並回傳；
        如果不符合，都不做，回傳None

        常用於可選的語法結構，ex.if self.match(TT.ELSE):
        """
        if self.check(*types):
            return self.advance()
        return None
    
    def expect(self, type_, msg=None):
        """
        「強制消耗」
        如果當前Token符合就消耗並回傳；
        如果不符合就拋出ParserError（語法錯誤）

        用於一定要出現的語法結構，ex.self.except(TT.SEMICOLON) => 必須有分號，沒有會報錯
                                or self.except(TT.RPAREN) => 括號必須閉合
        msg是自訂錯誤訊息，不傳的話會自動產生一個
        """
        tok = self.peek()
        if tok.type != type_:
            raise ParseError(
                msg or f"Expected {type_.name}, got {tok.value!r}",
                tok.line
            )
        return self.advance()
    
    def current_line(self):
        """回傳當前的Token行號，用來記錄AST節點是在第幾行"""
        return self.peek().line
    
    #程式進入點

    def parse_program(self):
        """
        解析整個程式
        不斷解析最外層宣告，直到遇到EOF
        回傳一個Program節點（樹根）
        """
        decls = []
        self.errors = []
        while not self.check(TT.EOF):
            try:
                decls.extend(self._parse_top_level())
            except ParseError as e:
                self.errors.append(e)
                self._synchronize()
        return Program(decls)
    
    def _parse_top_level(self):
        """
        解析最外層結構，回傳一個節點的list
        可能是：
        #define SIZE 8 => DefineDirective
        int x = 5; => VarDecl
        int main(){...} => FuncDef
        printf(" hello\n"); => ExprStmt(互動模式用)
        """
        if self.check(TT.HASH):
            return [self._parse_define()] # #define
        if self.match(TT.SEMICOLON):
            return [] #多餘的分號忽略
        if self.check(TT.INT, TT.CHAR, TT.VOID):
            return [self._parse_decl_or_func()] #變數宣告或函式定義
        return [self._parse_statement()] #互動模式下的裸陳述句
    
    def _parse_define(self):
        """
        解析#define指令
        格式 => # define 名稱 整數值
        """
        line = self.current_line()
        self.expect(TT.HASH) #消耗 #
        ident = self.expect(TT.IDENT) # 消耗define(當作識別字讀進來)       
        if ident.value != 'define':
            raise ParseError(f"Unknown prepocessor directive: {ident.value}", ident.line)
        name_tok = self.expect(TT.IDENT) #消耗常數名稱
        val_tok = self.expect(TT.INTEGER) #消耗整數值
        return DefineDirective(name_tok.value, val_tok.value, line)
    
    def _parse_decl_or_func(self):
        """
        解析「型別 名稱...」開頭的結構
        讀到（ 就是函式定義，否則是變數宣告

        函式定義 => int add(int a, int b) { return a + b; }
        變數宣告 => int x = 5; or int arr[10];
        """
        line = self.current_line()
        ret_type = self.advance().value #消耗型別int/char/void
        is_ptr = bool(self.match(TT.STAR)) #有*是指標
        name_tok = self.expect(TT.IDENT)
        name = name_tok.value

        if self.check(TT.LPAREN): #下一個是（ => 函式定義
            params = self._parse_param_list()
            body = self._parse_block()
            return FuncDef(ret_type, name, params, body, line)
        
        #否則是變數宣告，可能有[]表示陣列
        array_size = None
        if self.match(TT.LBRACKET): #有[ => 陣列宣告
            if self.check(TT.INTEGER):
                array_size = self.advance().value #數字大小
            elif self.check(TT.IDENT):
                array_size = Ident(self.advance().value, line) #define常數
            else:
                raise ParseError("Expected array size", self.current_line())
            self.expect(TT.RBRACKET) #消耗 ]

        init = None
        if self.match(TT.ASSIGN): #有 = => 初始值
            init = self._parse_assign_expr()
        self.expect(TT.SEMICOLON, "Expected ';' after variable declaration")
        return VarDecl(ret_type, name, is_ptr, array_size, init, line)
    
    def _parse_param_list(self):
        """
        解析函式參數列表，回傳list，每個元素是（型別字串, 參數名稱, 是否為指標）
        """
        self.expect(TT.LPAREN) #消耗（
        params = []
        if not self.check(TT.RPAREN): #括號不是空的
            while True:
                #void單獨出現在括號裡表示「沒有參數」，ex.int main(void)
                if self.check(TT.VOID) and self.peek(1).type == TT.RPAREN:
                    self.advance()
                    break
                params.append(self._parse_param())
                if not self.match(TT.COMMA): #沒有逗號表示參數讀完了
                    break
        self.expect(TT.RPAREN) # 消耗）
        return params

    def _parse_param(self):
        """
        解析單一參數。回傳（型別字串, 名稱, 是否為指標）的tuple。
        ex. int a => ('int', 'a', False)
            int *arr => ('int', 'arr', True)
            int arr[] => ('int', 'arr', True) <=[]視同指標 
        """
        type_tok = self.peek()
        if not self.check(TT.INT, TT.CHAR, TT.VOID):
            raise ParseError(f"Expected type inparameter, got {type_tok.value!r}", type_tok.line)
        type_str = self.advance().value
        is_ptr = bool(self.match(TT.STAR))
        name_tok = self.expect(TT.IDENT)
        if self.match(TT.LBRACKET): #arr[]的[]消耗掉，視為指標
            self.expect(TT.RBRACKET)
            is_ptr = True
        return (type_str, name_tok.value, is_ptr)
    
    #陳述句解析

    def _parse_block(self):
        """
        解析大括號區塊{陳述句...}
        """
        line = self.current_line()
        self.expect(TT.LBRACE) #消耗{
        stmts = []
        while not self.check(TT.RBRACE, TT.EOF): #遇到 } 或檔案結尾才停
            stmts.append(self._parse_statement())
        self.expect(TT.RBRACE)
        return Block(stmts, line)

    def _parse_statement(self):
        """
        解析陳述句，根據當前的Token種類決定路線，不做實際解析，只呼叫對應函式
        """
        line = self.current_line()

        if self.check(TT.INT, TT.CHAR, TT.VOID): return self._parse_local_decl()
        if self.check(TT.LBRACE): return self._parse_block()
        if self.match(TT.SEMICOLON): return EmptyStmt(line)
        if self.check(TT.IF): return self._parse_if()
        if self.check(TT.WHILE): return self._parse_while()
        if self.check(TT.FOR): return self._parse_for()
        if self.check(TT.DO): return self._parse_do_while()
        if self.check(TT.RETURN): return self._parse_return()
        if self.check(TT.SWITCH): return self._parse_switch()

        if self.check(TT.BREAK):
            self.advance()
            self.expect(TT.SEMICOLON)
            return BreakStmt(line)
        
        if self.check(TT.CONTINUE):
            self.advance()
            self.expect(TT.SEMICOLON)
            return ContinueStmt(line)
        
        #其他情況一定是運算式陳述句，如x = 5; 或 printf(...);
        expr = self._parse_assign_expr()
        self.expect(TT.SEMICOLON, "Expected ';' after expression statement")
        return ExprStmt(expr, line)
    
    def _parse_local_decl(self):
        """
        解析和函式內部的區域變數宣告。
        邏輯與_parse_decl_or_func的變數部分相同
        """
        line = self.current_line()
        type_str = self.advance().value
        is_ptr = bool(self.match(TT.STAR))
        name_tok = self.expect(TT.IDENT)
        name = name_tok.value

        array_size = None
        if self.match(TT.LBRACKET):
            if self.check(TT.INTEGER):
                array_size = self.advance().value
            elif self.check(TT.IDENT):
                array_size = Ident(self.advance().value, line)
            else:
                raise ParseError("Expected array size", self.current_line())
            self.expect(TT.RBRACKET)
        
        init = None
        if self.match(TT.ASSIGN):
            init = self._parse_assign_expr()
        
        self.expect(TT.SEMICOLON, "Expected ';' after variable declaration")
        return VarDecl(type_str, name, is_ptr, array_size, init, line)
    
    def _parse_if(self):
        """
        解析if/if-else
        格式 => if(條件)陳述句 [ else陳述句 ]
        """
        line = self.current_line()
        self.expect(TT.IF)
        self.expect(TT.LPAREN)
        cond = self._parse_assign_expr()
        self.expect(TT.RPAREN)
        then_stmt = self._parse_statement()
        else_stmt = None
        if self.match(TT.ELSE): #else是可選的
            else_stmt = self._parse_statement()
        return IfStmt(cond, then_stmt, else_stmt, line)
    
    def _parse_while(self):
        """
        解析while迴圈
        格式 => while（條件）陳述句
        """
        line = self.current_line()
        self.expect(TT.WHILE)
        self.expect(TT.LPAREN)
        cond = self._parse_assign_expr()
        self.expect(TT.RPAREN)
        body = self._parse_statement()
        return WhileStmt(cond, body, line)
    
    def _parse_for(self):
        """
        解析for
        格式 => for(初始化；條件；更新)陳述句

        **三個部分皆可省略
        for(;;) => 無限迴圈
        for(; i < n; ) => 省略初始化和更新
        """
        line = self.current_line()
        self.expect(TT.FOR)
        self.expect(TT.LPAREN)

        #初始化部分 => 空、變數宣告、或運算式
        if self.check(TT.SEMICOLON):
            init = None
            self.advance()
        elif self.check(TT.INT, TT.CHAR):
            # for (int i = 0;...)
            type_str = self.advance().value
            is_ptr = bool(self.match(TT.STAR))
            name_tok = self.expect(TT.IDENT)
            init_expr = None
            if self.match(TT.ASSIGN):
                init_expr = self._parse_assign_expr()
            init = VarDecl(type_str, name_tok.value, is_ptr, None, init_expr, line)
            self.expect(TT.SEMICOLON)
        else:
            init = self._parse_assign_expr() #一般運算式
            self.expect(TT.SEMICOLON)

        #條件部分：省略時視為永遠真(Intlit(1))
        if self.check(TT.SEMICOLON):
            cond = IntLit(1, line)
            self.advance()
        else:
            cond = self._parse_assign_expr()
            self.expect(TT.SEMICOLON)

        #更新：省略時為None
        if self.check(TT.RPAREN):
            update = None
        else:
            update = self._parse_assign_expr()

        self.expect(TT.RPAREN)
        body = self._parse_statement()
        return ForStmt(init, cond, update, body, line)
    
    def _parse_do_while(self):
        """
        解析do-while
        格式 => do陳述句，while條件;
        while後面的;不能省略
        """
        line =self.current_line()
        self.expect(TT.DO)
        body = self._parse_statement()
        self.expect(TT.WHILE)
        self.expect(TT.LPAREN)
        cond = self._parse_assign_expr()
        self.expect(TT.RPAREN)
        self.expect(TT.SEMICOLON) #do-while特有，結尾必須有分號
        return DoWhileStmt(body, cond, line)
    
    def _parse_return(self):
        """
        解析return 陳述句
        return; => 沒有回傳值（void用）
        return a + b; => 有回傳值
        """
        line = self.current_line()
        self.expect(TT.RETURN)
        if self.check(TT.SEMICOLON):
            self.advance()
            return ReturnStmt(None, line) #void函式的return
        expr = self._parse_assign_expr()
        self.expect(TT.SEMICOLON)
        return ReturnStmt(expr, line)
    
    #運算式解析（優先順序爬升法）
    #Parser核心，為了正確處理運算子優先順序，每個優先級皆對應一個函式
    #低優先呼叫高優先，形成呼叫鏈
    #assign -> or -> and -> bitor -> bitxor -> bitand -> equality -> relational -> shift -> additive -> multiplicative -> unary -> postfix -> primary
    #越往右優先級越高，先計算
    
    def _parse_assign_expr(self):
        """
        指定運算式（優先級最低）
        右結合：a = b = 5 => a = (b = 5)，遞迴呼叫自己
        """
        left = self._parse_or()
        assign_ops = {
            TT.ASSIGN: '=', TT.PLUS_ASSIGN: '+=',
            TT.MINUS_ASSIGN: '-=', TT.STAR_ASSIGN: '*=',
            TT.SLASH_ASSIGN: '/=', TT.MOD_ASSIGN: '%=',
        }
        if self.peek().type in assign_ops:
            op = assign_ops[self.advance().type]
            right = self._parse_assign_expr() #右結合：遞迴
            return Assign(op, left, right, self.current_line())
        return left
    
    def _parse_or(self):
        """ || 邏輯OR，左結合。"""
        left = self._parse_and()
        while self.check(TT.OR):
            line = self.current_line()
            self.advance()
            right = self._parse_and()
            left = BinOp('||', left, right, line)
        return left
    
    def _parse_and(self):
        """ && 邏輯AND，左結合。"""
        left = self._parse_bitor()
        while self.check(TT.AND):
            line = self.current_line()
            self.advance()
            right = self._parse_bitor()
            left = BinOp('&&', left, right, line)
        return left
    
    def _parse_bitor(self):
        """ | 位元OR，左結合。"""
        left = self._parse_bitxor()
        while self.check(TT.PIPE):
            line = self.current_line()
            self.advance()
            right = self._parse_bitxor()
            left = BinOp('|', left, right, line)
        return left
    
    def _parse_bitxor(self):
        """ ^位元 XOR，左結合。"""
        left = self._parse_bitand()
        while self.check(TT.CARET):
            line = self.current_line()
            self.advance()
            right = self._parse_bitand()
            left = BinOp('^', left, right, line)
        return left
    
    def _parse_bitand(self):
        """ &位元 AND，左結合。"""
        left = self._parse_equality()
        while self.check(TT.AMP):
            line = self.current_line()
            self.advance()
            right = self._parse_equality()
            left = BinOp('&', left, right, line)
        return left
    
    def _parse_equality(self):
        """ ==和!=相等比較，左結合。"""
        left = self._parse_relational()
        while self.check(TT.EQ, TT.NEQ):
            line = self.current_line()
            op = self.advance().value #'==' or '!='
            right = self._parse_relational()
            left = BinOp(op, left, right, line)
        return left
    
    def _parse_relational(self):
        """ <, >, <=, >= 大小比較，左結合。"""
        left = self._parse_shift()
        while self.check(TT.LT, TT.GT, TT.LE, TT.GE):
            line = self.current_line()
            op = self.advance().value
            right = self._parse_shift()
            left = BinOp(op, left, right, line)
        return left
    
    def _parse_shift(self):
        """ <<, >>位元位移，左結合。"""
        left = self._parse_additive()
        while self.check(TT.LSHIFT, TT.RSHIFT):
            line = self.current_line()
            op = self.advance().value
            right = self._parse_additive()
            left = BinOp(op, left, right, line)
        return left
    
    def _parse_additive(self):
        """ + - 加減法，左結合。"""
        left = self._parse_multiplicative()
        while self.check(TT.PLUS, TT.MINUS):
            line  = self.current_line()
            op    = self.advance().value
            right = self._parse_multiplicative()
            left  = BinOp(op, left, right, line)
        return left

    def _parse_multiplicative(self):
        """ */% 乘除餘，左結合。"""
        left = self._parse_unary()
        while self.check(TT.STAR, TT.SLASH, TT.PERCENT):
            line = self.current_line()
            op = self.advance().value
            right = self._parse_unary()
            left = BinOp(op, left, right, line)
        return left
    
    def _parse_unary(self):
        """  
        一元運算子，右結合（ 遞回呼叫自己）
        處理 => - ! ~ * & ++ --
        如果沒有一元運算子，就往下交給postfix
        """
        line = self.current_line()
        if self.check(TT.MINUS): self.advance(); return UnaryOp('-', self._parse_unary(), line)
        if self.check(TT.BANG): self.advance(); return UnaryOp('!', self._parse_unary(), line)
        if self.check(TT.TILDE): self.advance(); return UnaryOp('~', self._parse_unary(), line)
        if self.check(TT.STAR): self.advance(); return UnaryOp('*', self._parse_unary(), line)
        if self.check(TT.AMP): self.advance(); return UnaryOp('&', self._parse_unary(), line)
        if self.check(TT.PLUS_PLUS): self.advance(); return UnaryOp('++', self._parse_unary(), line)
        if self.check(TT.MINUS_MINUS): self.advance(); return UnaryOp('--', self._parse_unary(), line)
        return self._parse_postfix()
    
    def _parse_postfix(self):
        """
        後置運算
        目前只有arr[i]，先讀一個primary，在看後面有無[，有的話包一層ArrayIndex
        可以連續 => arr[i][j] -> ArrayIndex(ArrayIndex(arr, i), j)
        """
        expr = self._parse_primary()
        while True:
            line = self.current_line()
            if self.check(TT.LBRACKET):
                self.advance() #消耗 [
                idx = self._parse_assign_expr()
                self.expect(TT.RBRACKET) #消耗 ]
                expr = ArrayIndex(expr, idx, line)
            else:
                break
        return expr
    
    def _parse_primary(self):
        """ 
        最基本運算式（優先級最高）
        
        整數字面值 -> IntLit
        字元字面值 -> CharLit
        字串字面值 -> StringLit
        識別字 -> Ident / FuncCall（看最後有沒有括號）
        括號運算式 -> 遞迴解析括號內容
        """
        line = self.current_line()
        tok = self.peek()

        if tok.type == TT.INTEGER:
            self.advance()
            return IntLit(tok.value, line)
        
        if tok.type == TT.CHAR_LIT:
            self.advance()
            return CharLit(tok.value, line)
        
        if tok.type == TT.STRING:
            self.advance()
            return StringLit(tok.value, line)
        
        if tok.type == TT.IDENT:
            self.advance()
            name = tok.value
            if self.check(TT.LPAREN): #識別字後面有( -> 函式呼叫
                self.advance() #消耗(
                args = []
                if not self.check(TT.RPAREN):
                    args.append(self._parse_assign_expr())
                    while self.match(TT.COMMA): 
                        args.append(self._parse_assign_expr())
                self.expect(TT.RPAREN) #消耗 )
                return FuncCall(name, args, line)
            return Ident(name, line) #一般變數
        
        if tok.type == TT.LPAREN: #(運算式) -> 括號優先
            self.advance()
            expr = self._parse_assign_expr()
            self.expect(TT.RPAREN)
            return expr
        
        raise ParseError(f"Unexpected token in expression: {tok.value!r}", tok.line)
    
    def _parse_switch(self):
        """
        解析 switch 陳述句。
        格式：
            switch (expr) {
                case 1:
                    陳述句...
                case 2:
                    陳述句...
                default:
                    陳述句...
            }

        注意：
            每個 case 不需要 break 就會自動停止（不做 fall-through）
            如果要 fall-through 行為，之後可以再擴充
        """
        line = self.current_line()
        self.expect(TT.SWITCH)
        self.expect(TT.LPAREN)
        expr = self._parse_assign_expr()    # 比對的運算式
        self.expect(TT.RPAREN)
        self.expect(TT.LBRACE)             # 消耗 {

        cases         = []   # [(值, [stmts]), ...]
        default_stmts = None

        while not self.check(TT.RBRACE, TT.EOF):
            if self.check(TT.CASE):
                self.advance()                          # 消耗 case
                val_tok = self.expect(TT.INTEGER)       # 消耗數字
                self.expect(TT.COLON)                  # 消耗 :
                # 讀這個 case 的所有陳述句，直到下一個 case/default/}
                stmts = []
                while not self.check(TT.CASE, TT.DEFAULT, TT.RBRACE, TT.EOF):
                    stmts.append(self._parse_statement())
                cases.append((val_tok.value, stmts))

            elif self.check(TT.DEFAULT):
                self.advance()                          # 消耗 default
                self.expect(TT.COLON)                  # 消耗 :
                stmts = []
                while not self.check(TT.CASE, TT.DEFAULT, TT.RBRACE, TT.EOF):
                    stmts.append(self._parse_statement())
                default_stmts = stmts

            else:
                # 不認識的 Token，跳過避免無限迴圈
                self.advance()

        self.expect(TT.RBRACE)             # 消耗 }
        return SwitchStmt(expr, cases, default_stmts, line)
    
    def _synchronize(self):
        """
        錯誤恢復：遇到語法錯誤後，跳過Token直到找到
        一個安全的重新開始點（分號、大括號）
        這樣Parser才能繼續往下找下一個錯誤
        """
        if self.check(TT.EOF):
            return
        
        self.advance()
        
        while not self.check(TT.EOF):
            if self.check(TT.SEMICOLON):
                self.advance()
                return
            if self.check(TT.RBRACE, TT.LBRACE):
                return
            self.advance()