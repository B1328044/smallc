//遞迴呼叫
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

int main() {
    printf("5! = %d\n", factorial(5));
    printf("fib(7) = %d\n", fib(7));
    return 0;
}