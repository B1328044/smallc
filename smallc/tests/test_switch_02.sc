int grade(int score) {
    int g;
    g = score / 10;
    switch (g) {
        case 10:
            printf("A+\n");
        case 9:
            printf("A\n");
        case 8:
            printf("B\n");
        case 7:
            printf("C\n");
        default:
            printf("F\n");
    }
    return 0;
}

int main() {
    grade(95);
    grade(83);
    grade(72);
    grade(50);
    return 0;
}