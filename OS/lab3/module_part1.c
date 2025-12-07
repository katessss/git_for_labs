#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Student TSU");
MODULE_DESCRIPTION("TSU Lab Part 1");

static int __init tsu_init(void) {
    pr_info("Welcome to the Tomsk State University\n");
    return 0; 
}

static void __exit tsu_exit(void) {
    pr_info("Tomsk State University forever!\n");
}

module_init(tsu_init);
module_exit(tsu_exit);