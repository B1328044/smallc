# Small-C 互動式解譯器

**課程：** 系統軟體（System Software）  
**學期：** Spring 2026  
**作者：** B1328044/B1343055/B1245015

---

## 專案簡介

本專案實作一個 Small-C 語言的互動式解譯器，支援 Small-C 語言的詞法分析、語法分析、語意分析與執行，並提供完整的互動式 REPL 環境。

---

## 專案結構

```
smallc/
├── main.py
├── README.md
├── src/
│   ├── __init__.py
│   ├── ast_nodes.py
│   ├── builtins.py
│   ├── interpreter.py
│   ├── lexer.py
│   ├── memory.py
│   ├── parser.py
│   ├── repl.py
│   └── symtable.py
└── tests/
    ├── test_01_arithmetic.sc
    ├── test_01_arithmetic.expected
    ├── test_02_variables.sc
    ├── test_02_variables.expected
    ├── test_03_ifelse.sc
    ├── test_03_ifelse.expected
    ├── test_04_loops.sc
    ├── test_04_loops.expected
    ├── test_05_functions.sc
    ├── test_05_functions.expected
    ├── test_06_recursion.sc
    ├── test_06_recursion.expected
    ├── test_07_array.sc
    ├── test_07_array.expected
    ├── test_08_pointer.sc
    ├── test_08_pointer.expected
    ├── test_09_syntax_error.sc
    ├── test_09_syntax_error.expected
    ├── test_10_runtime_error.sc
    ├── test_10_runtime_error.expected
    ├── test_switch_01.sc
    ├── test_switch_01.expected
    ├── test_switch_02.sc
    ├── test_switch_02.expected
    ├── test_define_01.sc
    ├── test_define_01.expected
    ├── test_define_02.sc
    ├── test_define_02.expected
    ├── test_runtime_01.sc
    ├── test_runtime_01.expected
    ├── test_runtime_02.sc
    └── test_runtime_02.expected
```

---

## 環境需求

- Python 3.10 以上
- 不需要安裝任何額外套件

---

## 啟動方式

```bash
python3 main.py
```

或指定作者名稱：

```bash
python3 main.py --author "你的名字"
```

---

## 支援的語言特性

### 資料型別
- `int`、`char`
- 指標（`*`、`&`）
- 一維陣列

### 運算子
- 算術：`+`、`-`、`*`、`/`、`%`
- 關係：`<`、`>`、`<=`、`>=`、`==`、`!=`
- 邏輯：`&&`、`||`、`!`（含短路求值）
- 位元：`&`、`|`、`^`、`~`、`<<`、`>>`
- 複合指定：`+=`、`-=`、`*=`、`/=`、`%=`

### 控制結構
- `if` / `else`
- `while`
- `for`
- `do-while`
- `break`、`continue`
- `switch` / `case` / `default`

### 其他
- 函式定義與遞迴呼叫
- `#define` 常數替換
- 單行註解 `//` 與區塊註解 `/* */`
- 十六進位常數（`0x`）
- 字元與跳脫序列（`\n`、`\t`、`\0` 等）

### 內建函式

| 類別 | 函式 |
|------|------|
| I/O | `printf`、`scanf`、`putchar`、`getchar`、`puts` |
| 字串 | `strlen`、`strcpy`、`strcmp`、`strcat` |
| 數學 | `abs`、`max`、`min`、`pow`、`sqrt`、`mod` |
| 工具 | `rand`、`srand`、`atoi`、`itoa`、`memset`、`exit` |

---

## 互動環境指令

| 指令 | 說明 |
|------|------|
| `APPEND` | 附加程式碼到緩衝區尾端 |
| `LIST [n] [n1-n2]` | 顯示緩衝區內容 |
| `EDIT <n>` | 編輯第 n 行 |
| `DELETE <n>` | 刪除第 n 行 |
| `INSERT <n>` | 在第 n 行前插入 |
| `NEW` | 清除緩衝區 |
| `LOAD <檔案>` | 載入 .sc 檔案 |
| `SAVE <檔案>` | 儲存到檔案 |
| `RUN` | 執行程式 |
| `CHECK` | 語法檢查 |
| `TRACE ON/OFF` | 開關逐行追蹤模式 |
| `VARS` | 顯示所有全域變數 |
| `FUNCS` | 顯示所有函式 |
| `HELP` | 顯示說明 |
| `ABOUT` | 顯示版本資訊 |
| `CLEAR` | 清除畫面 |
| `QUIT` / `EXIT` | 離開解譯器 |

---

## 執行測試

```bash
sc> LOAD tests/test_01_arithmetic.sc
sc> RUN
```

對照對應的 `.expected` 檔案確認輸出是否一致。

---

## 錯誤處理

解譯器會偵測並回報以下錯誤：

- **語法錯誤**：缺少分號、括號不匹配等
- **執行期錯誤**：
  - 除以零
  - 陣列索引越界
  - 空指標取值
  - 使用未定義的變數或函式
