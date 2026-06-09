//ifelse條件分支、while迴圈
int main() {
    int x = 10;
    if (x > 5) {
        printf("big\n");
    } else {
        printf("small\n");
    }
    int i = 0;
    while (i < 5) {
        printf("%d ", i);
        i = i + 1;
    }
    printf("\n");
    return 0;
}