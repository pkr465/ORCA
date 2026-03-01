// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (C) 2026 Example Corp
 *
 * Sample well-formatted kernel-style C file.
 */

#include <linux/module.h>
#include <linux/kernel.h>

#include "sample_good.h"

static int module_param_value = 42;

/**
 * sample_init - Initialize the sample module
 *
 * Return: 0 on success, negative errno on failure
 */
static int sample_init(void)
{
	int ret;

	ret = do_something(module_param_value);
	if (ret < 0)
		goto err_cleanup;

	pr_info("Sample module initialized\n");
	return 0;

err_cleanup:
	pr_err("Initialization failed: %d\n", ret);
	return ret;
}

static void sample_exit(void)
{
	pr_info("Sample module exiting\n");
}

module_init(sample_init);
module_exit(sample_exit);

MODULE_LICENSE("GPL v2");
MODULE_AUTHOR("Example Corp");
