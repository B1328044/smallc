"""
repl.py — 互動殼層（REPL）

REPL 是 Read-Eval-Print Loop 的縮寫：
    Read  → 讀取使用者輸入
    Eval  → 判斷是指令還是程式碼，執行它
    Print → 顯示結果
    Loop  → 回到開頭，繼續等待輸入

這個檔案是使用者看到的那一層，
負責處理所有互動指令（LOAD、RUN、LIST 等），
以及把直接輸入的 Small-C 程式碼交給 Interpreter 執行。

REPL 本身不理解程式碼，
它只負責「管理緩衝區」和「分派工作給其他模組」。
"""

import os
import sys
import re

from .lexer       import tokenize, LexerError
from .parser      import Parser, ParseError
from .interpreter import Interpreter, RuntimeError_
from .builtins    import ExitSignal, BUILTIN_SIGNATURES
from .ast_nodes import (
    Program, FuncDef, VarDecl, DefineDirective,
    Block, IfStmt, WhileStmt, ForStmt, DoWhileStmt,
    ReturnStmt, BreakStmt, ContinueStmt, ExprStmt, EmptyStmt,
    IntLit, CharLit, StringLit, Ident,
    BinOp, UnaryOp, Assign, ArrayIndex, FuncCall
)

# ── 常數設定 ──────────────────────────────────────────────────

VERSION        = "1.0"
COURSE         = "Spring 2026"
PROMPT         = "sc> "          # 一般提示符
CONT_PROMPT_FMT = "{:>4}> "      # APPEND/INSERT 時的行號提示符，如 "   1> "

# HELP 指令顯示的完整說明文字
HELP_TEXT = """Available commands:
  LOAD <filename>   - Load a Small-C source file into the program buffer
  SAVE <filename>   - Save the current program buffer to a file
  LIST              - List the entire program buffer
  LIST <n>          - List line n
  LIST <n1>-<n2>    - List lines n1 through n2
  EDIT <n>          - Edit line n
  DELETE <n>        - Delete line n
  DELETE <n1>-<n2>  - Delete lines n1 through n2
  INSERT <n>        - Insert lines before line n
  APPEND            - Append lines to the end of the buffer
  NEW               - Clear the program buffer and reset state
  RUN               - Run the current program
  CHECK             - Check the program for syntax/semantic errors
  TRACE ON          - Enable execution trace mode
  TRACE OFF         - Disable execution trace mode
  VARS              - Display all global variables and their values
  FUNCS             - List all defined functions
  HELP              - Show this help message
  HELP <command>    - Show detailed help for a command
  ABOUT             - Show interpreter information
  CLEAR             - Clear the terminal screen
  QUIT / EXIT       - Exit the interpreter
"""

# HELP <指令名稱> 的詳細說明
HELP_DETAIL = {
    'LOAD':   'LOAD <filename>\n  Loads a Small-C source file into the program buffer.\n  Overwrites current buffer (prompts if unsaved changes).',
    'SAVE':   'SAVE <filename>\n  Saves the program buffer to the specified file.',
    'LIST':   'LIST [n] [n1-n2]\n  Lists program lines. No argument = all lines.',
    'EDIT':   'EDIT <n>\n  Shows line n and allows you to replace it. Press Enter to keep original.',
    'DELETE': 'DELETE <n> or DELETE <n1>-<n2>\n  Deletes one or a range of lines.',
    'INSERT': 'INSERT <n>\n  Enters insert mode before line n. Type "." to end.',
    'APPEND': 'APPEND\n  Appends lines to the end of the buffer. Type "." to end.',
    'NEW':    'NEW\n  Clears buffer and resets all state.',
    'RUN':    'RUN\n  Executes the program in the buffer.',
    'CHECK':  'CHECK\n  Checks for syntax/semantic errors without running.',
    'TRACE':  'TRACE ON/OFF\n  Enables or disables line-by-line execution tracing.',
    'VARS':   'VARS\n  Displays all global variables with their current values.',
    'FUNCS':  'FUNCS\n  Lists all user-defined and built-in functions.',
    'HELP':   'HELP [command]\n  Displays help. Optionally for a specific command.',
    'ABOUT':  'ABOUT\n  Displays interpreter name, version, author, and course.',
    'CLEAR':  'CLEAR\n  Clears the terminal screen.',
    'QUIT':   'QUIT / EXIT\n  Exits the interpreter.',
    'EXIT':   'QUIT / EXIT\n  Exits the interpreter.',
}


class REPL:
    def __init__(self, stdin=None, stdout=None, author="Student"):
        """
        stdin/stdout 預設是終端機，但可以換成其他串流，
        方便測試時用假的輸入輸出取代真實的鍵盤螢幕。

        _buffer   : 程式緩衝區，每個元素是一行程式碼的字串
        _modified : 緩衝區有未儲存的修改時為 True，
                    QUIT/NEW/LOAD 前會提示使用者確認
        _trace    : TRACE ON/OFF 的狀態
        """
        self._stdin  = stdin  or sys.stdin
        self._stdout = stdout or sys.stdout
        self._author = author

        self._buffer: list[str]  = []
        self._modified           = False
        self._saved_file: str | None = None
        self._trace              = False

        # 建立 Interpreter，把輸出/輸入/追蹤的回呼函式都指向 REPL 自己的方法
        # 這樣 printf 的輸出才會正確顯示在 REPL 的畫面上
        self._interp = Interpreter(
            output_cb = self._write,
            input_cb  = self._read_line,
            trace_cb  = self._trace_line,
        )

    # ── I/O 輔助方法 ──────────────────────────────────────────

    def _write(self, s: str):
        """不換行輸出，給 printf 等函式用。"""
        self._stdout.write(s)
        self._stdout.flush()

    def _writeln(self, s: str = ''):
        """換行輸出，給 REPL 自己的訊息用。"""
        self._stdout.write(s + '\n')
        self._stdout.flush()

    def _read_line(self) -> str:
        """讀一行輸入（給 scanf/getchar 用）。"""
        return self._stdin.readline().rstrip('\n')

    def _read_input(self, prompt='') -> str | None:
        """
        顯示提示符並讀一行輸入（給 REPL 本身用）。
        回傳 None 表示 EOF（使用者按了 Ctrl+D / 輸入結束）。
        """
        try:
            if prompt:
                self._stdout.write(prompt)
                self._stdout.flush()
            line = self._stdin.readline()
            if line == '':
                return None   # EOF
            return line.rstrip('\n')
        except (EOFError, KeyboardInterrupt):
            return None

    # ── TRACE 回呼 ────────────────────────────────────────────

    def _trace_line(self, line_no: int, stmt):
        """
        TRACE ON 模式下，Interpreter 每執行一條陳述句前都會呼叫這個函式。
        顯示格式：[line  5] int i;
        從緩衝區取出對應行的原始程式碼文字一起顯示，比只顯示行號更好讀。
        """
        stmt_text = ''
        if 0 < line_no <= len(self._buffer):
            stmt_text = self._buffer[line_no - 1].strip()
        self._writeln(f"[line {line_no:2}] {stmt_text}")

    # ── 主迴圈 ────────────────────────────────────────────────

    def run(self):
        """
        REPL 的主迴圈，啟動後一直執行直到使用者 QUIT。
        每次迭代：
            1. 顯示提示符 sc>
            2. 讀取一行輸入
            3. 交給 _dispatch 判斷並執行
            4. 如果 _dispatch 回傳 True，表示要結束，跳出迴圈
        """
        self._print_banner()
        self._writeln("Type `HELP` for a list of commands.")
        self._writeln()
        while True:
            line = self._read_input(PROMPT)
            if line is None:       # EOF（Ctrl+D）
                self._writeln("\nGoodbye.")
                break
            line = line.strip()
            if not line:
                continue           # 空白行，直接等下一行
            should_exit = self._dispatch(line)
            if should_exit:
                break

    def _print_banner(self):
        """啟動時顯示的歡迎畫面。"""
        sep    = "=" * 44
        banner = sep + "\n"
        banner += "  Small-C Interactive Interpreter v" + VERSION + "\n"
        banner += "  System Software Final Project, " + COURSE + "\n"
        banner += sep
        self._writeln(banner)

    # ── 指令分派 ──────────────────────────────────────────────

    def _dispatch(self, line: str) -> bool:
        """
        判斷輸入是哪個指令，呼叫對應的處理方法。
        回傳 True 表示要結束 REPL，False 表示繼續。

        判斷方式：取輸入的第一個單字（轉大寫），比對所有指令名稱。
        如果沒有符合的指令，就當作 Small-C 程式碼執行。
        """
        upper = line.upper()
        first = upper.split()[0] if upper.split() else ''

        if first in ('QUIT', 'EXIT'): return self._cmd_quit()
        if first == 'ABOUT':   self._cmd_about();  return False
        if first == 'HELP':
            parts = line.split(None, 1)
            self._cmd_help(parts[1].upper().strip() if len(parts) > 1 else '')
            return False
        if first == 'CLEAR':   self._cmd_clear();  return False
        if first == 'NEW':     self._cmd_new();    return False
        if first == 'APPEND':  self._cmd_append(); return False
        if first == 'LIST':
            self._cmd_list(line[4:].strip())
            return False
        if first == 'EDIT':
            parts = line.split()
            if len(parts) < 2 or not parts[1].isdigit():
                self._writeln("Usage: EDIT <n>")
                return False
            self._cmd_edit(int(parts[1]))
            return False
        if first == 'DELETE':
            self._cmd_delete(line[6:].strip())
            return False
        if first == 'INSERT':
            parts = line.split()
            if len(parts) < 2 or not parts[1].isdigit():
                self._writeln("Usage: INSERT <n>")
                return False
            self._cmd_insert(int(parts[1]))
            return False
        if first == 'SAVE':
            parts = line.split(None, 1)
            if len(parts) < 2:
                self._writeln("Usage: SAVE <filename>")
                return False
            self._cmd_save(parts[1].strip())
            return False
        if first == 'LOAD':
            parts = line.split(None, 1)
            if len(parts) < 2:
                self._writeln("Usage: LOAD <filename>")
                return False
            self._cmd_load(parts[1].strip())
            return False
        if first == 'RUN':     self._cmd_run();   return False
        if first == 'CHECK':   self._cmd_check(); return False
        if first == 'TRACE':
            self._cmd_trace(line[5:].strip().upper())
            return False
        if first == 'VARS':    self._cmd_vars();  return False
        if first == 'FUNCS':   self._cmd_funcs(); return False

        # 不是指令 → 當作 Small-C 程式碼在互動模式下執行
        self._exec_interactive_code(line)
        return False

    # ── 各指令實作 ────────────────────────────────────────────

    def _cmd_about(self):
        self._writeln(f"Small-C Interactive Interpreter v{VERSION}")
        self._writeln(f"Course: System Software, {COURSE}")
        self._writeln(f"Author: {self._author}")

    def _cmd_help(self, cmd: str):
        """有帶指令名稱就顯示詳細說明，否則顯示全部指令清單。"""
        if cmd and cmd in HELP_DETAIL:
            self._writeln(HELP_DETAIL[cmd])
        else:
            self._write(HELP_TEXT)

    def _cmd_clear(self):
        """清除終端機畫面，Windows 用 cls，其他用 clear。"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _cmd_quit(self) -> bool:
        """
        結束解譯器。
        如果有未儲存的修改，先問使用者是否確認。
        """
        if self._modified:
            ans = self._read_input("Unsaved changes. Quit anyway? (y/n): ")
            if ans is None or ans.strip().lower() not in ('y', 'yes'):
                return False
        self._writeln("Goodbye.")
        return True

    def _cmd_new(self, silent=False):
        """
        清除緩衝區和所有執行狀態，回到空白起點。
        silent=True 用於程式內部呼叫，不顯示確認提示。
        """
        if self._modified and not silent:
            ans = self._read_input("Unsaved changes. Clear anyway? (y/n): ")
            if ans is None or ans.strip().lower() not in ('y', 'yes'):
                return
        self._buffer.clear()
        self._modified   = False
        self._saved_file = None
        self._interp.reset()
        self._writeln("All cleared.")

    def _cmd_append(self):
        """
        進入附加模式，讓使用者一行一行輸入程式碼加到緩衝區尾端。
        顯示行號提示符（如 "   1> "），輸入單獨一個 . 結束。
        """
        line_no   = len(self._buffer) + 1
        new_lines = []
        while True:
            inp = self._read_input(CONT_PROMPT_FMT.format(line_no))
            if inp is None or inp.strip() == '.':
                break
            new_lines.append(inp)
            line_no += 1
        self._buffer.extend(new_lines)
        if new_lines:
            self._modified = True

    def _cmd_list(self, spec: str):
        """
        顯示緩衝區內容。
        spec 可以是：
            空字串   → 顯示全部
            "56"     → 顯示第 56 行
            "1-5"    → 顯示第 1 到 5 行
        行號格式固定為四位數，對齊方便閱讀。
        """
        if not self._buffer:
            self._writeln("(program buffer is empty)")
            return
        if not spec:
            for i, line in enumerate(self._buffer, 1):
                self._writeln(f"{i:4}: {line}")
            return
        m = re.match(r'^(\d+)-(\d+)$', spec)   # 用正則判斷是否為 n1-n2 格式
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            for i in range(n1, min(n2, len(self._buffer)) + 1):
                self._writeln(f"{i:4}: {self._buffer[i-1]}")
            return
        if spec.isdigit():
            n = int(spec)
            if 1 <= n <= len(self._buffer):
                self._writeln(f"{n:4}: {self._buffer[n-1]}")
            else:
                self._writeln(f"Line {n} does not exist.")
            return
        self._writeln(f"Invalid LIST argument: {spec}")

    def _cmd_edit(self, n: int):
        """
        顯示第 n 行的內容，讓使用者輸入新內容取代。
        直接按 Enter（空輸入）表示保留原始內容不變。
        """
        if n < 1 or n > len(self._buffer):
            self._writeln(f"Line {n} does not exist.")
            return
        current = self._buffer[n - 1]
        self._writeln(f"{n:4}: {current}")     # 顯示目前內容
        new_line = self._read_input("     ")   # 等待新輸入
        if new_line is None or new_line == '':
            return                             # 空輸入，保留原始
        self._buffer[n - 1] = new_line
        self._modified = True

    def _cmd_delete(self, spec: str):
        """
        刪除一行或一個範圍的行。
        刪除後，後面的行號自動往前遞減。
        Python 的 list 切片刪除：del self._buffer[n1-1:n2]
        """
        if not spec:
            self._writeln("Usage: DELETE <n> or DELETE <n1>-<n2>")
            return
        m = re.match(r'^(\d+)-(\d+)$', spec)
        if m:
            n1 = max(1, int(m.group(1)))
            n2 = min(int(m.group(2)), len(self._buffer))
            if n1 > n2:
                self._writeln("Invalid range.")
                return
            del self._buffer[n1-1:n2]   # 切片刪除，一次刪多行
            self._modified = True
            return
        if spec.isdigit():
            n = int(spec)
            if 1 <= n <= len(self._buffer):
                del self._buffer[n-1]
                self._modified = True
            else:
                self._writeln(f"Line {n} does not exist.")
            return
        self._writeln(f"Invalid DELETE argument: {spec}")

    def _cmd_insert(self, n: int):
        """
        在第 n 行之前插入新行。
        進入插入模式後，輸入 . 結束。
        使用 Python list 的切片賦值：self._buffer[pos:pos] = new_lines
        這會把 new_lines 插入到 pos 位置，不覆蓋原有內容。
        """
        n = max(1, min(n, len(self._buffer) + 1))
        ins_pos   = n - 1
        new_lines = []
        line_no   = n
        while True:
            inp = self._read_input(CONT_PROMPT_FMT.format(line_no))
            if inp is None or inp.strip() == '.':
                break
            new_lines.append(inp)
            line_no += 1
        self._buffer[ins_pos:ins_pos] = new_lines   # 插入，不覆蓋
        if new_lines:
            self._modified = True

    def _cmd_save(self, filename: str):
        """
        把緩衝區內容存成檔案，每行加換行符號。
        儲存成功後把 _modified 設為 False。
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for line in self._buffer:
                    f.write(line + '\n')
            self._modified   = False
            self._saved_file = filename
            self._writeln(f"Saved {len(self._buffer)} lines to '{filename}'.")
        except OSError as e:
            self._writeln(f"Error saving file: {e}")

    def _cmd_load(self, filename: str):
        """
        從檔案載入程式碼到緩衝區。
        splitlines() 把檔案內容按換行切成 list，不保留換行符號。
        載入後重置 Interpreter 狀態（清除之前執行的殘留）。
        """
        if self._modified:
            ans = self._read_input("Unsaved changes. Load anyway? (y/n): ")
            if ans is None or ans.strip().lower() not in ('y', 'yes'):
                return
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
            self._buffer     = lines
            self._modified   = False
            self._saved_file = filename
            self._interp.reset()
            self._writeln(f"Loaded {len(lines)} lines from '{filename}'.")
        except FileNotFoundError:
            self._writeln(f"Error: file '{filename}' not found.")
        except OSError as e:
            self._writeln(f"Error loading file: {e}")

    def _cmd_run(self):
        """
        執行緩衝區裡的程式。
        步驟：
        1. 把緩衝區所有行合併成一個字串
        2. Lexer → Parser → AST
        3. 語法有錯就停下來顯示錯誤，不執行
        4. Interpreter 執行 AST
        5. 捕捉所有可能的錯誤，顯示訊息，不讓解譯器崩潰
        """  
        if not self._buffer:
            self._writeln("Program buffer is empty.")
            return
        source = '\n'.join(self._buffer)
        try:
            tokens  = tokenize(source)
            parser  = Parser(tokens)
            program = parser.parse_program()   # ← 存起來

            if parser.errors:
                self._writeln(f"Syntax errors found. Use CHECK for details.")
                return

        except LexerError as e:
            self._writeln(f"Syntax error: {e}")
            return
        except ParseError as e:
            self._writeln(f"Syntax error at line {e.line}: {e}")
            return

        self._interp.reset()
        self._interp.trace_mode = self._trace

        try:
            ret = self._interp.execute_program(program)   # ← 用存起來的 program
            self._writeln(f"Program exited with return value {ret}.")
        except ExitSignal as e:
            self._writeln(f"Program exited with return value {e.code}.")
        except RuntimeError_ as e:
            self._writeln(f"Runtime error: {e}")
        except RecursionError:
            self._writeln("Runtime error: stack overflow (infinite recursion?)")
        except Exception as e:
            self._writeln(f"Internal error: {e}")
    def _cmd_check(self):
        """
        只做語法檢查，不執行程式。
        把緩衝區內容跑過 Lexer + Parser，
        有錯就顯示錯誤訊息，沒錯就顯示 No errors found.
        """
        if not self._buffer:
            self._writeln("Program buffer is empty.")
            return
        source = '\n'.join(self._buffer)
        errors = []
        
        try:
            tokens = tokenize(source)
            parser = Parser(tokens)
            parser.parse_program()
            for e in sorted(parser.errors, key=lambda x: x.line):
                errors.append(f"Error at line {e.line}: {e}")       
        except LexerError as e:
            errors.append(f"Lexical error at line {e.line}: {e}")
        
        if errors:
            for err in errors:
                self._writeln(err)
            self._writeln(f"{len(errors)} error(s) found.")
        else:
            self._writeln("No errors found.")

    def _cmd_trace(self, arg: str):
        """開關 TRACE 模式，同時更新 REPL 自己的狀態和 Interpreter 的狀態。"""
        if arg == 'ON':
            self._trace              = True
            self._interp.trace_mode = True
            self._writeln("Trace mode enabled.")
        elif arg == 'OFF':
            self._trace              = False
            self._interp.trace_mode = False
            self._writeln("Trace mode disabled.")
        else:
            self._writeln("Usage: TRACE ON | TRACE OFF")

    def _cmd_vars(self):
        """顯示所有全域變數，委託給 Interpreter 的 get_vars_display。"""
        lines = self._interp.get_vars_display()
        if not lines:
            self._writeln("(no global variables)")
        else:
            for l in lines:
                self._writeln(l)

    def _cmd_funcs(self):
        """
        顯示所有函式：先列使用者定義函式，再列內建函式。
        使用者定義函式的資訊從 Interpreter 的符號表取得，
        內建函式的資訊從 BUILTIN_SIGNATURES 取得。
        """
        funcs = self._interp.symtable.functions
        if funcs:
            for name, info in funcs.items():
                params_str = ', '.join(
                    f"{t}{'*' if p else ''} {n}" for t, n, p in info.params
                )
                self._writeln(f"  {info.ret_type} {name}({params_str})  \t\tline {info.line}")
        self._writeln("  --- built-in functions ---")
        for ret, name, params in BUILTIN_SIGNATURES:
            params_str = ', '.join(f"{t} {n}" for t, n, _ in params)
            self._writeln(f"  {ret} {name}({params_str})  \t\t[built-in]")

    # ── 互動模式程式碼執行 ────────────────────────────────────

    def _exec_interactive_code(self, first_line: str):
        """
        處理在 sc> 提示符下直接輸入的 Small-C 程式碼。

        難點：多行輸入。
        如果使用者輸入 void foo() {，這行沒有 }，
        代表輸入還沒結束，需要繼續讀下一行。

        做法：計算大括號的「深度」（{ 加一，} 減一），
        深度 > 0 就繼續讀，直到深度回到 0。
        """
        lines = [first_line]
        depth = _brace_depth(first_line)   # 計算這行的括號深度

        while depth > 0:
            inp = self._read_input("  > ")   # 顯示縮排提示，等待繼續輸入
            if inp is None:
                break
            lines.append(inp)
            depth += _brace_depth(inp)       # 累計括號深度

        source = '\n'.join(lines)
        self._exec_source_interactive(source)

    def _exec_source_interactive(self, source: str):
        """
        把一段程式碼字串用 Lexer + Parser 解析後，
        交給 Interpreter 的互動模式執行。
        每個宣告/陳述句分開執行，這樣執行到一半出錯時
        前面已執行的部分不會被撤銷。
        """
        try:
            tokens = tokenize(source)
        except LexerError as e:
            self._writeln(f"Syntax error: {e}")
            return

        try:
            program = Parser(tokens).parse_program()
        except ParseError as e:
            self._writeln(f"Syntax error at line {e.line}: {e}")
            return

        self._interp.trace_mode = self._trace

        for decl in program.decls:
            try:
                self._interp.exec_interactive(decl)
            except ExitSignal as e:
                self._writeln(f"Program exited with return value {e.code}.")
                return
            except RuntimeError_ as e:
                self._writeln(str(e))
                return
            except RecursionError:
                self._writeln("Runtime error: stack overflow (infinite recursion?)")
                return
            except Exception as e:
                self._writeln(f"Internal error: {type(e).__name__}: {e}")
                return


# ── 模組層級輔助函式 ──────────────────────────────────────────

def _brace_depth(line: str) -> int:
    """
    計算一行程式碼中大括號的淨深度（{ 加一，} 減一）。
    用來判斷多行輸入是否已完整。

    注意：字串和字元裡的括號不算。
    例如：printf("{");  這行的淨深度是 0，不是 1。

    做法：用 in_str 和 in_char 旗標追蹤目前是否在引號內，
    在引號內的括號直接跳過。
    """
    depth   = 0
    in_str  = False   # 目前是否在 "..." 裡面
    in_char = False   # 目前是否在 '...' 裡面
    i = 0
    while i < len(line):
        c = line[i]
        if c == '\\' and (in_str or in_char):
            i += 2    # 跳脫序列（如 \"），跳過兩個字元
            continue
        if c == '"' and not in_char:
            in_str = not in_str
        elif c == "'" and not in_str:
            in_char = not in_char
        elif not in_str and not in_char:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
        i += 1
    return depth