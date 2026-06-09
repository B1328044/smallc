//陣列大小和迴圈邊界
#define ROWS 3
#define COLS 3

int main() {
    int i;
    int j;
    for (i = 1; i <= ROWS; i = i + 1) {
        for (j = 1; j <= COLS; j = j + 1) {
            printf("%d ", i * j);
        }
        printf("\n");
    }
    return 0;
}