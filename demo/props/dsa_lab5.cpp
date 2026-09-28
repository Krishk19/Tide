#include <stdio.h>
#include <string.h>
int is_private(int a, int b) {
    if (a == 10) return 1;
    if (a == 172 && b >= 16 && b <= 31) return 1;
    if (a == 192 && b == 168) return 1;
    return 0;
}
char cls(int a) {
    if (a < 128) return 'A';
    if (a < 192) return 'B';
    if (a < 224) return 'C';
    if (a < 240) return 'D';
    return 'E';
}
int main(void) {
    int n, a, b, c, d;
    scanf("%d", &n);
    while (n--) {
        scanf("%d.%d.%d.%d", &a, &b, &c, &d);
        printf("%c %s\n", cls(a), is_private(a, b) ? "private" : "public");
    }
    return 0;
}
