//陣列操作
int main() {
    int arr[5];
    int i;
    for (i = 0; i < 5; i = i + 1) {
        arr[i] = (i + 1) * 10;
    }
    for (i = 0; i < 5; i = i + 1) {
        printf("%d ", arr[i]);
    }
    printf("\n");
    printf("max=%d\n", max(arr[0], arr[4]));
    return 0;
}