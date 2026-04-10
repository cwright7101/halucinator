#include <assert.h>

void immediate_return() {}

void layered_return(int input) {
  // Force a call to immediate_return (will be optimized away otherwise)
  __asm__("bl immediate_return");
}

int main() {
  // Force a call to layered_return (will be optimized away otherwise)
  __asm__("bl layered_return");
  return 0;
}
