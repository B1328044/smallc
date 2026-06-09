"""
lexer.py
詞法分析器，解譯的第一個動作 => 將義整段原始碼「字串」切成多個有意義的小單元「Tokens」（詞元）

ex. input = int x = 25;
    output Token = [INT, IDENT("x"), ASSIGN, INTEGER(25), SEMICOLON, EOF]

**notice**
    Lexer不理解語法，只是認識字元或字元組合的代表符號
    理解語法 => Parser 
"""

import re
from enum import Enum, auto

#TokenType定義所有可能的Token種類
#使用Python的Enum讓每一個種類都有唯一的識別名稱
#auto()自動指派一個不重複的整數值，也就是我們不在乎實際是多少

class TokenType(Enum):
    #字面值（literals）: 整數、字元、字串、識別字
    INTEGER = auto()
    CHAR_LIT = auto()
    STRING = auto()
    IDENT = auto()     #不是關鍵字的名稱ex. x, myFunc...  

    #關鍵字（keywords）
    #C語言的保留字，不能當變數名稱使用
    INT = auto()
    CHAR =auto()
    VOID = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    DO = auto()
    BREAK = auto()
    CONTINUE =auto()
    RETURN = auto()
    SWITCH = auto()
    CASE = auto()
    DEFAULT = auto()

    #運算子（Operators）
    PLUS = auto()
    MINUS = auto()
    STAR = auto() # *
    SLASH = auto() # /
    PERCENT = auto() # % 
    AMP = auto() # &
    PIPE = auto() # |
    CARET = auto() # ^
    TILDE = auto() # ~
    BANG = auto() # !
    LT = auto() # <
    GT = auto() # >
    LE = auto() # <=
    GE = auto() # >=
    EQ = auto() # ==
    NEQ = auto() # !=
    AND = auto() # &&
    OR = auto() # ||
    LSHIFT = auto() # <<
    RSHIFT = auto() # >>
    ASSIGN = auto() # =(assign)

    #複合指定運算子
    PLUS_ASSIGN = auto() # +=
    MINUS_ASSIGN = auto() # -=
    STAR_ASSIGN = auto() # *=
    SLASH_ASSIGN = auto() # /=
    MOD_ASSIGN = auto()# %=

    #前置遞增/遞減
    PLUS_PLUS = auto() # ++
    MINUS_MINUS = auto() # --

    #分隔符號（Delimiters）
    LPAREN = auto() # (
    RPAREN = auto() # )
    LBRACE = auto() # {
    RBRACE = auto() # }
    LBRACKET = auto() # [
    RBRACKET = auto() # ]
    SEMICOLON = auto() # ;
    COMMA = auto() # ,
    COLON = auto() # :

    #特殊符號
    HASH = auto() # #(define用)
    EOF =auto() # 檔案結尾標記，告訴Parser已經沒有Token了

    #KEYWORDS：把關鍵字字串對應到TokenType
    #當Lexer讀到一個字，先查這個表。找到=>是關鍵字，用對應的TokenType;沒找到=>是一般識別字，用IDENT。

KEYWORDS = {
    'int': TokenType.INT,
    'char': TokenType.CHAR,
    'void': TokenType.VOID,
    'if': TokenType.IF,
    'else': TokenType.ELSE,
    'while': TokenType.WHILE,
    'for': TokenType.FOR,
    'do': TokenType.DO,
    'break': TokenType.BREAK,
    'continue': TokenType.CONTINUE,
    'return': TokenType.RETURN,
    'switch': TokenType.SWITCH,
    'case': TokenType.CASE,
    'default': TokenType.DEFAULT,
}

#代表一個詞元的資料結構

class Token:
    """
    一個Token紀錄：
       type => 符號種類
       value => 原始內容
                INTEGER => Python int
                IDENT => 字串（ex."myFunc"）
                運算子 => 字串（ex."+="）
       line => 出現在原始碼的第幾行
    """
    def __init__(self, type_, value, line=0):
        self.type = type_
        self.value = value
        self.line = line

    def __repr__(self):
        #讓print(token)的輸出更好讀，除錯時用
        return f'Token({self.type}, {self.value!r}, line={self.line})'
    
#LexerError:詞法分析階段的錯誤

class LexerError(Exception):
    """
    遇到無法辨識的字元會拋出，line可以讓上層顯示「第幾行」出錯
    """
    def __init__(self, msg, line=0):
        super().__init__(msg)
        self.line = line


#_parse_escape:把跳脫序列轉成真正的字元

def _parse_escape(ch):
    """
    遇到反斜線後面的字元時，查這個表轉換
    ex."\\n" => 換行字元
       "\\t" => 定位字元
       "\\0" => 空字元
       "\\\\" => 反斜線本身
       若不在表中（如\\a），直接回傳原字元。
    """
    return {
        'n': '\n', # 換行
        't': '\t', # 水平定位
        '0': '\0', # 空字元（C字串結尾標記）
        '\\': '\\', # 反斜線本身
        "'": "'", # 單引號
        '"': '"', # 雙引號
        'r': '\r', # 歸位字元
    }.get(ch, ch) # 找不到就回傳ch本身


#tokenize:主要函式，把整段原始碼切成 Token 串列

def tokenize(source, start_line=1):
    """
    輸入：source => 完整的Small-C原始碼字串
         start_line => 起始行號（互動模式下可以指定）
    輸出：Token物件的list，最後一個永遠是EOF Token

    實作：
        用手工掃描。
        用游標pos從頭掃到尾，
        每次辨識出一種Token就把pos往後移，
        直到掃完整個字串。
    """
    tokens = []
    pos = 0
    line = start_line
    n = len(source)

    while pos < n:

        #跳過空白字元
        if source[pos] in ' \t\r':
            pos += 1
            continue

        #換行，跳過並讓行號加一
        if source[pos] == '\n':
            line += 1
            pos += 1
            continue

        #單行註節//，從//開始到該行結尾全部忽略
        if source[pos:pos+2] == '//':
            while pos < n and source[pos] != '\n':
                pos += 1
            continue #換行會在下一次迴圈被處理，避免行號誤加

        #區塊註解/*...*/，可以跨行，要更新行數
        if source[pos:pos+2] == '/*':
            pos += 2 #跳過/*
            while pos < n and source[pos-1:pos+1] != '*/':
                if source[pos] == '\n':
                    line += 1
                pos += 1
            if pos < n:
                pos += 1 #跳過最後的 /，讓游標停在*/之後
            continue

        # #號（#define用）
        #Lexer只認得出#，#define交給Parser處理
        if source[pos] == '#':
            tokens.append(Token(TokenType.HASH, '#', line))
            pos += 1
            continue

        #字串字面值 "..."
        if source[pos] == '"':
            pos += 1 #跳過開頭的 "
            s = [] #收集字串內的字元
            while pos < n and source[pos] != '"':
                if source[pos] == '\\' and pos + 1 < n:
                    #遇到反斜線，讀下一個字元並跳脫轉換
                    pos += 1
                    s.append(_parse_escape(source[pos]))
                else:
                    if source[pos] == '\n':
                        line += 1
                    s.append(source[pos])
                pos += 1
            if pos < n:
                pos += 1 #跳過結尾的"
            #value是已處理跳脫序列的Python字串
            tokens.append(Token(TokenType.STRING, ''.join(s), line))
            continue
        
        #字元字面值'...'
        if source[pos] == "'":
            pos += 1 #跳過開頭的'
            if pos < n and source[pos] == '\\' and pos + 1 < n:
                #跳脫字元'\n','\t'...
                pos += 1
                ch = _parse_escape(source[pos])
                pos += 1
            elif pos < n:
                #一般字元
                ch = source[pos]
                pos += 1
            else:
                raise LexerError("Unterminated character literal", line)
            if pos < n and source[pos] == "'":
                pos += 1 #跳過結尾的'
            #value存的是ACSII整數，Interpreter處理字元和整數可用同樣邏輯
            tokens.append(Token(TokenType.CHAR_LIT, ord(ch), line))
            continue

        #16進位整數0x...，必須在十進位數字判斷之前處理，否則會被當成十進位獨走
        if source[pos:pos+2] in ('0x', '0X'):
            pos += 2 #跳過0x前綴
            start = pos
            while pos < n and source[pos] in '0123456789abcdefABCDEF':
                pos += 1
            tokens.append(Token(TokenType.INTEGER, int(source[start:pos], 16), line))
            continue
        #10進位整數
        if source[pos].isdigit():
            start = pos
            while pos < n and source[pos].isdigit():
                pos += 1
            tokens.append(Token(TokenType.INTEGER,int(source[start:pos]), line))
            continue

        #識別字或關鍵字，識別字 => 開頭是字母或底線，後面可以跟字母、數字、底線
        if source[pos].isalpha() or source[pos] == '_':
            start = pos
            while pos < n and (source[pos].isalnum() or source[pos] == '_'):
                pos += 1
            word = source[start:pos]
            #查KEYWORD表：是關鍵字就用關鍵字的type，否則就是IDENT
            tt = KEYWORDS.get(word, TokenType.IDENT)
            tokens.append(Token(tt, word, line))
            continue

        #雙字元運算子（要在單字元之前先判斷）
        two = source[pos:pos+2]
        two_map = {
            '&&': TokenType.AND, '||': TokenType.OR,
            '<<':TokenType.LSHIFT, '>>': TokenType.RSHIFT,
            '<=':TokenType.LE, '>=': TokenType.GE,
            '==':TokenType.EQ, '!=': TokenType.NEQ,
            '+=':TokenType.PLUS_ASSIGN, '-=':TokenType.MINUS_ASSIGN,
            '*=':TokenType.STAR_ASSIGN, '/=':TokenType.SLASH_ASSIGN,
            '%=':TokenType.MOD_ASSIGN,
            '++':TokenType.PLUS_PLUS, '--':TokenType.MINUS_MINUS,
        }
        if two in two_map:
            tokens.append(Token(two_map[two], two, line))
            pos += 2
            continue

        #單原子運算子和分隔符號
        one_map = {
            '+': TokenType.PLUS, '-': TokenType.MINUS,
            '*': TokenType.STAR, '/': TokenType.SLASH,
            '%': TokenType.PERCENT, '&': TokenType.AMP,
            '|': TokenType.PIPE, '^': TokenType.CARET,
            '~': TokenType.TILDE, '!': TokenType.BANG,
            '<': TokenType.LT, '>': TokenType.GT,
            '=': TokenType.ASSIGN,
            '(': TokenType.LPAREN, ')': TokenType.RPAREN,
            '{': TokenType.LBRACE, '}': TokenType.RBRACE,
            '[': TokenType.LBRACKET, ']': TokenType.RBRACKET,
            ';': TokenType.SEMICOLON, ',': TokenType.COMMA,
            ':': TokenType.COLON,
        }
        if source[pos] in one_map:
            tokens.append(Token(one_map[source[pos]], source[pos], line))
            pos += 1
            continue

        #表時無法辨識
        raise LexerError(f"Unexpected character: {source[pos]!r}", line)

    #補上EOF Token，Parser才知道原始碼結束
    tokens.append(Token(TokenType.EOF, None, line))
    return tokens                