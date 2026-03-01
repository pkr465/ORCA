// Missing SPDX identifier
// Missing proper copyright information
#ifndef BAD_STYLE_H  // Wrong guard style - should use #ifndef GUARD_H and end with #endif
#define BAD_STYLE_H

#include <linux/types.h>
#include "other.h"  // Own header after system header - wrong order

/* No Doxygen comments for exported items */
int process_data(const char *data, int len);
void cleanup(void);

typedef struct {
    int field1;
    char field2;  // Wrong member naming - should be snake_case
} BadStruct;

#define BAD_MACRO(x) x * x  // Missing parens around args
#define MULTILINE(a, b) \
	if (a) \
		do_thing(b)         // No do-while wrapper

/* Function pointer with unclear naming */
typedef int (*FuncPtr)(void *);

#endif  // BAD_STYLE_H - redundant comment
