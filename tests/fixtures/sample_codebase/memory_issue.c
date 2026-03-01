// SPDX-License-Identifier: GPL-2.0-only
/*
 * Example file with structure-related issues for testing
 */

#include <linux/kernel.h>
#include <linux/slab.h>

#include "memory_issue.h"

/* Structure with alignment issues */
typedef struct {
	char a;          /* 1 byte */
	long b;          /* 8 bytes - alignment gap before this */
	char c;          /* 1 byte */
	int d;           /* 4 bytes - alignment gap before this */
	char e;          /* 1 byte */
	/* Padding holes could be optimized */
} UnalignedStruct;

/* Function pointer typedef without void * */
typedef int (*callback_t)(int, int);

/* Global function without static (bad for encapsulation) */
int process_data_internal(void *data)
{
	return 0;
}

/* Missing locks on shared resource */
static struct resource_t {
	int count;
	char buffer[256];
} global_resource;

/* Forward declaration issues */
static void helper_function(void);

static int main_function(void)
{
	/* Nested function definitions not allowed in C */
	helper_function();
	return 0;
}

static void helper_function(void)
{
	global_resource.count++;
}
