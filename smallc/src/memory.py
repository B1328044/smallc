"""
memory.py — 模擬記憶體

為什麼需要「模擬」記憶體？
    Small-C 支援指標（*p、&x）和陣列（arr[i]），
    這些功能的本質是「用一個整數位址去存取記憶體」。

    Python 本身不讓你直接操作記憶體位址，
    所以我們用一個字典來「假裝」是一塊記憶體：
        key   = 整數位址（如 1000、1001、1002...）
        value = 該位址存放的整數值

    這樣就能完整模擬 C 語言的指標行為：
        int x = 25;      → 在位址 1000 寫入 25
        int *p = &x;     → 在位址 1001 寫入 1000（x 的位址）
        printf("%d", *p) → 讀位址 1001 得到 1000，再讀位址 1000 得到 25
"""


class MemoryError(Exception):
    """存取未配置的記憶體位址時拋出。"""
    def __init__(self, msg):
        super().__init__(msg)


class Memory:

    HEAP_START = 1000
    # 位址從 1000 開始，而不是從 0 開始。
    # 原因：C 語言慣例上用 0 表示 NULL 指標（空指標），
    #       代表「不指向任何東西」。
    #       如果從 0 開始配置，就沒辦法區分「位址 0」和「NULL」了。

    def __init__(self):
        self._cells: dict[int, int] = {}
        # _cells 就是整塊模擬記憶體：
        #     key   → 整數位址
        #     value → 該格存放的整數值
        # 用字典而不是 list 的原因：
        #     只有實際配置過的位址才會出現在字典裡，
        #     存取沒有配置過的位址會被 read/write 偵測到並報錯。

        self._next_addr = self.HEAP_START
        # 下一次 alloc 要從哪個位址開始配置。
        # 每次配置後這個值就往後移，確保不同變數不會佔到同一格。

    def alloc(self, size: int) -> int:
        """
        配置 size 格連續記憶體，回傳起始位址。

        例如：
            alloc(1)  → 配置 1 格，用於純量變數（int x）
            alloc(8)  → 配置 8 格，用於陣列（int arr[8]）

        每格初始值為 0，對應 C 語言「全域變數預設為零」的規則。
        """
        addr = self._next_addr          # 記錄這次的起始位址
        for i in range(size):
            self._cells[addr + i] = 0   # 把每格初始化為 0
        self._next_addr += size         # 下次從這裡之後繼續配置
        return addr                     # 回傳起始位址

    def read(self, addr: int) -> int:
        """
        讀取位址 addr 的值。
        如果該位址從未被配置過，就報錯（對應 C 語言的未定義行為）。
        """
        if addr not in self._cells:
            raise MemoryError(f"Read from unallocated address {addr}")
        return self._cells[addr]

    def write(self, addr: int, value: int):
        """
        把 value 寫入位址 addr。
        value 強制轉成 int，確保不會意外存入浮點數。
        """
        if addr not in self._cells:
            raise MemoryError(f"Write to unallocated address {addr}")
        self._cells[addr] = int(value)

    def write_string(self, addr: int, s: str):
        """
        把一個 Python 字串以 C 字串格式寫入記憶體。

        C 字串的格式：每個字元佔一格（存 ASCII 整數），
        最後加一個值為 0 的格子作為結尾標記（null terminator）。

        例如，"hi" 寫入位址 1000：
            1000 → 104  ('h' 的 ASCII)
            1001 → 105  ('i' 的 ASCII)
            1002 → 0    (字串結尾)

        strlen、printf 的 %s 都靠這個 0 來判斷字串在哪裡結束。
        """
        for i, ch in enumerate(s):
            self.write(addr + i, ord(ch))   # ord('h') = 104
        self.write(addr + len(s), 0)        # 寫入結尾的 0

    def read_string(self, addr: int) -> str:
        """
        從位址 addr 讀取一個 C 字串，回傳 Python str。
        一直讀到遇到值為 0 的格子為止。

        v & 0xFF 是取低 8 位元，確保只處理一個 byte 範圍的字元（0～255）。

        安全限制：如果讀超過 10000 個字元還沒遇到 0，
        表示可能忘了寫結尾，直接報錯，避免無限迴圈。
        """
        result = []
        i = 0
        while True:
            v = self.read(addr + i)
            if v == 0:
                break                       # 遇到 null terminator，字串結束
            result.append(chr(v & 0xFF))    # 整數轉回字元
            i += 1
            if i > 10000:
                raise MemoryError("String read exceeded limit (possible missing null terminator)")
        return ''.join(result)

    def ensure_addr(self, addr: int, size: int = 1):
        """
        確保位址 addr 到 addr+size-1 都存在於 _cells 中。
        如果不存在就初始化為 0。
        用於指標運算時，目標位址可能還沒被正式 alloc 過的情況。
        """
        for i in range(size):
            if addr + i not in self._cells:
                self._cells[addr + i] = 0

    def reset(self):
        """
        清空所有記憶體，位址計數器歸回起點。
        每次 RUN 之前都會呼叫，確保上次執行的殘留值不會影響這次。
        """
        self._cells.clear()
        self._next_addr = self.HEAP_START