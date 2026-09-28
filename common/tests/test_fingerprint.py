from tide_common.fingerprint import fingerprints, normalize_code, similarity, tokens

ORIGINAL = """
#include <stdio.h>
// count vowels
int main() {
    char s[100]; int count = 0;
    scanf("%s", s);
    for (int i = 0; s[i] != '\\0'; i++) {
        if (s[i]=='a'||s[i]=='e'||s[i]=='i'||s[i]=='o'||s[i]=='u') count++;
    }
    printf("%d\\n", count);
    return 0;
}
"""

RENAMED = """
#include <stdio.h>
int main() {
    char word[100]; int total = 0;   /* renamed */
    scanf("%s", word);
    for (int j = 0; word[j] != '\\0'; j++) {
        if (word[j]=='a'||word[j]=='e'||word[j]=='i'||word[j]=='o'||word[j]=='u') total++;
    }
    printf("%d\\n", total);
    return 0;
}
"""

UNRELATED = """
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
print(sum(fib(k) for k in range(10)))
"""


def test_normalize_strips_comments_and_whitespace():
    assert normalize_code("int  a; // hi\n/* x */ b") == "int a; b"


def test_identifiers_collapse_keywords_stay():
    assert tokens("int count = 0;") == ["int", "v", "=", "0", ";"]


def test_renamed_copy_is_similar():
    assert similarity(fingerprints(ORIGINAL), fingerprints(RENAMED)) >= 0.8


def test_unrelated_is_not_similar():
    assert similarity(fingerprints(ORIGINAL), fingerprints(UNRELATED)) < 0.3


def test_empty_is_zero():
    assert similarity(fingerprints(""), fingerprints(ORIGINAL)) == 0.0


def test_stable_across_calls():
    assert fingerprints(ORIGINAL) == fingerprints(ORIGINAL)
