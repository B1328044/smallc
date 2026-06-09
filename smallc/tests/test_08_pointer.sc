//指標操作
void increment(int *p) {
    *p = *p + 1;
}

int main() {
    int x = 10;
    increment(&x);
    printf("x=%d\n", x);
    int arr[3];
    arr[0] = 1;
    arr[1] = 2;
    arr[2] = 3;
    int *p = &arr[0];
    printf("%d %d %d\n", *p, arr[1], arr[2]);
    return 0;
}