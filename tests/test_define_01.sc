//條件判斷和運算
#define TRUE 1
#define FALSE 0
#define PASS 60

int main() {
    int score = 75;
    if (score >= PASS) {
        printf("passed=%d\n", TRUE);
    } else {
        printf("passed=%d\n", FALSE);
    }
    printf("diff=%d\n", score - PASS);
    return 0;
}