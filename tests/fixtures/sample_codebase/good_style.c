// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (C) 2026 Example Corporation
 *
 * This is a properly formatted C source file demonstrating
 * full compliance with Linux kernel style guidelines.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>

#include "good_style.h"

/* Module parameters */
static int param_value = 100;
module_param(param_value, int, 0644);

/**
 * calculate_checksum - Calculate checksum for data
 * @data: Pointer to data buffer
 * @len: Length of data in bytes
 *
 * Return: Computed checksum value
 */
static uint32_t calculate_checksum(const uint8_t *data, int len)
{
	uint32_t sum = 0;
	int i;

	for (i = 0; i < len; i++)
		sum += data[i];

	return sum;
}

/**
 * process_buffer - Process a data buffer
 * @buffer: Input buffer to process
 * @size: Size of buffer
 *
 * Return: 0 on success, negative errno on failure
 */
static int process_buffer(const char *buffer, size_t size)
{
	if (!buffer || size == 0)
		return -EINVAL;

	if (size > MAX_BUFFER_SIZE) {
		pr_err("Buffer size %zu exceeds maximum %d\n",
		       size, MAX_BUFFER_SIZE);
		return -ERANGE;
	}

	return 0;
}

/**
 * module_init - Initialize the module
 *
 * Return: 0 on success, negative errno on failure
 */
static int __init good_init(void)
{
	int ret;

	pr_info("Initializing good_style module\n");

	ret = process_buffer(NULL, 0);
	if (ret < 0) {
		pr_err("Failed to process buffer: %d\n", ret);
		return ret;
	}

	pr_info("Module initialized successfully\n");
	return 0;
}

/**
 * module_exit - Clean up the module
 */
static void __exit good_exit(void)
{
	pr_info("Exiting good_style module\n");
}

module_init(good_init);
module_exit(good_exit);

MODULE_LICENSE("GPL v2");
MODULE_AUTHOR("Example Corporation <example@corp.com>");
MODULE_DESCRIPTION("Example kernel module with proper style");
MODULE_VERSION("1.0");
