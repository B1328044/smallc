//for迴圈、continue跳過迭代、do-while迴圈
int main() {
    int i;
    for (i = 1; i <= 5; i = i + 1) {
        if (i % 2 == 0) continue;
        printf("%d ", i);
    }
    printf("\n");
    int n = 1;
    do {
        printf("%d ", n);
        n = n * 2;
    } while (n <= 16);
    printf("\n");
    return 0;
}