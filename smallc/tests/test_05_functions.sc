//函式定義
int add(int a, int b) {
    return a + b;
}

int square(int x) {
    return x * x;
}

int main() {
    printf("%d\n", add(3, 4));
    printf("%d\n", square(5));
    printf("%d\n", add(square(2), square(3)));
    return 0;
}