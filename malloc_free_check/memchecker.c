#include <stdio.h>
#include <stdlib.h>

int
main(void)
{
    int i;

    for (i = 1; i < 20; ++i)
    {
        int *addr = (int *)malloc(10 * sizeof(int));
        printf("Address allocated: %p\n", addr);

        if (!(i % 10 == 0))
        {
            printf("Address freed: %p\n", addr);
            free(addr);
        }
    }
}
