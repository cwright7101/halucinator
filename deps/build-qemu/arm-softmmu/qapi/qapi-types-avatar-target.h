/* AUTOMATICALLY GENERATED, DO NOT MODIFY */

/*
 * Schema-defined QAPI types
 *
 * Copyright IBM, Corp. 2011
 * Copyright (c) 2013-2018 Red Hat Inc.
 *
 * This work is licensed under the terms of the GNU LGPL, version 2.1 or later.
 * See the COPYING.LIB file in the top-level directory.
 */

#ifndef QAPI_TYPES_AVATAR_TARGET_H
#define QAPI_TYPES_AVATAR_TARGET_H

#include "qapi/qapi-builtin-types.h"

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
typedef struct q_obj_avatar_armv7m_enable_irq_arg q_obj_avatar_armv7m_enable_irq_arg;
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
typedef struct q_obj_avatar_armv7m_inject_irq_arg q_obj_avatar_armv7m_inject_irq_arg;
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
typedef struct q_obj_avatar_armv7m_ignore_irq_return_arg q_obj_avatar_armv7m_ignore_irq_return_arg;
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
typedef struct q_obj_avatar_armv7m_unignore_irq_return_arg q_obj_avatar_armv7m_unignore_irq_return_arg;
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
typedef struct q_obj_avatar_armv7m_set_vector_table_base_arg q_obj_avatar_armv7m_set_vector_table_base_arg;
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
struct q_obj_avatar_armv7m_enable_irq_arg {
    char *irq_rx_queue_name;
    char *irq_tx_queue_name;
    char *rmem_rx_queue_name;
    char *rmem_tx_queue_name;
};
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
struct q_obj_avatar_armv7m_inject_irq_arg {
    int64_t num_cpu;
    int64_t num_irq;
};
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
struct q_obj_avatar_armv7m_ignore_irq_return_arg {
    int64_t num_irq;
};
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
struct q_obj_avatar_armv7m_unignore_irq_return_arg {
    int64_t num_irq;
};
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
struct q_obj_avatar_armv7m_set_vector_table_base_arg {
    int64_t num_cpu;
    int64_t base;
};
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#endif /* QAPI_TYPES_AVATAR_TARGET_H */
