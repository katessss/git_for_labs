#include <linux/module.h> 
#include <linux/kernel.h> 
#include <linux/init.h>  
#include <linux/proc_fs.h> 
#include <linux/uaccess.h>  
#include <linux/version.h> 

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Student of TSU");
MODULE_DESCRIPTION("OS Lab 3 Part 2");

#define FILENAME "tsulab" 
static struct proc_dir_entry *our_proc_file = NULL;

// ИНДИВИДУАЛЬНОЕ ЗАДАНИЕ
static void calculate_result(char *buffer, size_t max_len) {
    u64 current_time_sec = ktime_get_real_seconds();

    const u64 start_time_sec = (u64)-28893254400LL; 
    u64 total_seconds = current_time_sec - start_time_sec;
    u64 total_days = total_seconds / (60 * 60 * 24);

    snprintf(buffer, max_len, 
             "Возраст Крабовидной туманности: %llu дней\n", total_days);
}


static ssize_t my_super_read(struct file *file_pointer, char __user *buffer, size_t buffer_length, loff_t *offset) {
    char s[256];
    int len; 
    
    if (*offset > 0) 
        return 0;

    calculate_result(s, sizeof(s));
    len = strlen(s);

    if (len > buffer_length) 
        len = buffer_length;

    if (copy_to_user(buffer, s, len)) 
        return -EFAULT;
        
    *offset += len;
    pr_info("Procfile read: %s\n", FILENAME); 
    
    return len;
}


#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 6, 0)
static const struct proc_ops proc_file_fops = {
    .proc_read = my_super_read,
};
#else
static const struct file_operations proc_file_fops = {
    .read = my_super_read,
};
#endif

static int __init tsu_init(void) {
    pr_info("Welcome to the Tomsk State University\n");    
    our_proc_file = proc_create(FILENAME, 0644, NULL, &proc_file_fops);
    
    if (our_proc_file == NULL) {
        pr_alert("Error: Could not initialize /proc/%s\n", FILENAME);
        return -ENOMEM; 
    }
    
    pr_info("/proc/%s created\n", FILENAME);
    return 0;
}

static void __exit tsu_exit(void) {
    proc_remove(our_proc_file);
    pr_info("/proc/%s removed\n", FILENAME);
    pr_info("Tomsk State University forever!\n");
}

module_init(tsu_init);
module_exit(tsu_exit);