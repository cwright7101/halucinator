/* AUTOMATICALLY GENERATED, DO NOT MODIFY */

/*
 * Schema-defined QAPI visitors
 *
 * Copyright IBM, Corp. 2011
 * Copyright (C) 2014-2018 Red Hat, Inc.
 *
 * This work is licensed under the terms of the GNU LGPL, version 2.1 or later.
 * See the COPYING.LIB file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qapi/qmp/qerror.h"
#include "qapi-visit-avatar-target.h"

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_enable_irq_arg_members(Visitor *v, q_obj_avatar_armv7m_enable_irq_arg *obj, Error **errp)
{
    if (!visit_type_str(v, "irq-rx-queue-name", &obj->irq_rx_queue_name, errp)) {
        return false;
    }
    if (!visit_type_str(v, "irq-tx-queue-name", &obj->irq_tx_queue_name, errp)) {
        return false;
    }
    if (!visit_type_str(v, "rmem-rx-queue-name", &obj->rmem_rx_queue_name, errp)) {
        return false;
    }
    if (!visit_type_str(v, "rmem-tx-queue-name", &obj->rmem_tx_queue_name, errp)) {
        return false;
    }
    return true;
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_inject_irq_arg_members(Visitor *v, q_obj_avatar_armv7m_inject_irq_arg *obj, Error **errp)
{
    if (!visit_type_int(v, "num-cpu", &obj->num_cpu, errp)) {
        return false;
    }
    if (!visit_type_int(v, "num-irq", &obj->num_irq, errp)) {
        return false;
    }
    return true;
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_ignore_irq_return_arg_members(Visitor *v, q_obj_avatar_armv7m_ignore_irq_return_arg *obj, Error **errp)
{
    if (!visit_type_int(v, "num-irq", &obj->num_irq, errp)) {
        return false;
    }
    return true;
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_unignore_irq_return_arg_members(Visitor *v, q_obj_avatar_armv7m_unignore_irq_return_arg *obj, Error **errp)
{
    if (!visit_type_int(v, "num-irq", &obj->num_irq, errp)) {
        return false;
    }
    return true;
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_set_vector_table_base_arg_members(Visitor *v, q_obj_avatar_armv7m_set_vector_table_base_arg *obj, Error **errp)
{
    if (!visit_type_int(v, "num-cpu", &obj->num_cpu, errp)) {
        return false;
    }
    if (!visit_type_int(v, "base", &obj->base, errp)) {
        return false;
    }
    return true;
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

/* Dummy declaration to prevent empty .o file */
char qapi_dummy_qapi_visit_avatar_target_c;
