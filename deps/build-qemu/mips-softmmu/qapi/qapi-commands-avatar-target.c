/* AUTOMATICALLY GENERATED, DO NOT MODIFY */

/*
 * Schema-defined QAPI/QMP commands
 *
 * Copyright IBM, Corp. 2011
 * Copyright (C) 2014-2018 Red Hat, Inc.
 *
 * This work is licensed under the terms of the GNU LGPL, version 2.1 or later.
 * See the COPYING.LIB file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "qapi/compat-policy.h"
#include "qapi/visitor.h"
#include "qapi/qmp/qdict.h"
#include "qapi/dealloc-visitor.h"
#include "qapi/error.h"
#include "qapi-visit-avatar-target.h"
#include "qapi-commands-avatar-target.h"


#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_marshal_avatar_armv7m_enable_irq(QDict *args, QObject **ret, Error **errp)
{
    Error *err = NULL;
    bool ok = false;
    Visitor *v;
    q_obj_avatar_armv7m_enable_irq_arg arg = {0};

    v = qobject_input_visitor_new_qmp(QOBJECT(args));
    if (!visit_start_struct(v, NULL, NULL, 0, errp)) {
        goto out;
    }
    if (visit_type_q_obj_avatar_armv7m_enable_irq_arg_members(v, &arg, errp)) {
        ok = visit_check_struct(v, errp);
    }
    visit_end_struct(v, NULL);
    if (!ok) {
        goto out;
    }

    qmp_avatar_armv7m_enable_irq(arg.irq_rx_queue_name, arg.irq_tx_queue_name, arg.rmem_rx_queue_name, arg.rmem_tx_queue_name, &err);
    error_propagate(errp, err);

out:
    visit_free(v);
    v = qapi_dealloc_visitor_new();
    visit_start_struct(v, NULL, NULL, 0, NULL);
    visit_type_q_obj_avatar_armv7m_enable_irq_arg_members(v, &arg, NULL);
    visit_end_struct(v, NULL);
    visit_free(v);
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_marshal_avatar_armv7m_disable_irq(QDict *args, QObject **ret, Error **errp)
{
    Error *err = NULL;
    bool ok = false;
    Visitor *v;

    v = qobject_input_visitor_new_qmp(QOBJECT(args));
    if (!visit_start_struct(v, NULL, NULL, 0, errp)) {
        goto out;
    }
    ok = visit_check_struct(v, errp);
    visit_end_struct(v, NULL);
    if (!ok) {
        goto out;
    }

    qmp_avatar_armv7m_disable_irq(&err);
    error_propagate(errp, err);

out:
    visit_free(v);
    v = qapi_dealloc_visitor_new();
    visit_start_struct(v, NULL, NULL, 0, NULL);
    visit_end_struct(v, NULL);
    visit_free(v);
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_marshal_avatar_armv7m_inject_irq(QDict *args, QObject **ret, Error **errp)
{
    Error *err = NULL;
    bool ok = false;
    Visitor *v;
    q_obj_avatar_armv7m_inject_irq_arg arg = {0};

    v = qobject_input_visitor_new_qmp(QOBJECT(args));
    if (!visit_start_struct(v, NULL, NULL, 0, errp)) {
        goto out;
    }
    if (visit_type_q_obj_avatar_armv7m_inject_irq_arg_members(v, &arg, errp)) {
        ok = visit_check_struct(v, errp);
    }
    visit_end_struct(v, NULL);
    if (!ok) {
        goto out;
    }

    qmp_avatar_armv7m_inject_irq(arg.num_cpu, arg.num_irq, &err);
    error_propagate(errp, err);

out:
    visit_free(v);
    v = qapi_dealloc_visitor_new();
    visit_start_struct(v, NULL, NULL, 0, NULL);
    visit_type_q_obj_avatar_armv7m_inject_irq_arg_members(v, &arg, NULL);
    visit_end_struct(v, NULL);
    visit_free(v);
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_marshal_avatar_armv7m_ignore_irq_return(QDict *args, QObject **ret, Error **errp)
{
    Error *err = NULL;
    bool ok = false;
    Visitor *v;
    q_obj_avatar_armv7m_ignore_irq_return_arg arg = {0};

    v = qobject_input_visitor_new_qmp(QOBJECT(args));
    if (!visit_start_struct(v, NULL, NULL, 0, errp)) {
        goto out;
    }
    if (visit_type_q_obj_avatar_armv7m_ignore_irq_return_arg_members(v, &arg, errp)) {
        ok = visit_check_struct(v, errp);
    }
    visit_end_struct(v, NULL);
    if (!ok) {
        goto out;
    }

    qmp_avatar_armv7m_ignore_irq_return(arg.num_irq, &err);
    error_propagate(errp, err);

out:
    visit_free(v);
    v = qapi_dealloc_visitor_new();
    visit_start_struct(v, NULL, NULL, 0, NULL);
    visit_type_q_obj_avatar_armv7m_ignore_irq_return_arg_members(v, &arg, NULL);
    visit_end_struct(v, NULL);
    visit_free(v);
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_marshal_avatar_armv7m_unignore_irq_return(QDict *args, QObject **ret, Error **errp)
{
    Error *err = NULL;
    bool ok = false;
    Visitor *v;
    q_obj_avatar_armv7m_unignore_irq_return_arg arg = {0};

    v = qobject_input_visitor_new_qmp(QOBJECT(args));
    if (!visit_start_struct(v, NULL, NULL, 0, errp)) {
        goto out;
    }
    if (visit_type_q_obj_avatar_armv7m_unignore_irq_return_arg_members(v, &arg, errp)) {
        ok = visit_check_struct(v, errp);
    }
    visit_end_struct(v, NULL);
    if (!ok) {
        goto out;
    }

    qmp_avatar_armv7m_unignore_irq_return(arg.num_irq, &err);
    error_propagate(errp, err);

out:
    visit_free(v);
    v = qapi_dealloc_visitor_new();
    visit_start_struct(v, NULL, NULL, 0, NULL);
    visit_type_q_obj_avatar_armv7m_unignore_irq_return_arg_members(v, &arg, NULL);
    visit_end_struct(v, NULL);
    visit_free(v);
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_marshal_avatar_armv7m_set_vector_table_base(QDict *args, QObject **ret, Error **errp)
{
    Error *err = NULL;
    bool ok = false;
    Visitor *v;
    q_obj_avatar_armv7m_set_vector_table_base_arg arg = {0};

    v = qobject_input_visitor_new_qmp(QOBJECT(args));
    if (!visit_start_struct(v, NULL, NULL, 0, errp)) {
        goto out;
    }
    if (visit_type_q_obj_avatar_armv7m_set_vector_table_base_arg_members(v, &arg, errp)) {
        ok = visit_check_struct(v, errp);
    }
    visit_end_struct(v, NULL);
    if (!ok) {
        goto out;
    }

    qmp_avatar_armv7m_set_vector_table_base(arg.num_cpu, arg.base, &err);
    error_propagate(errp, err);

out:
    visit_free(v);
    v = qapi_dealloc_visitor_new();
    visit_start_struct(v, NULL, NULL, 0, NULL);
    visit_type_q_obj_avatar_armv7m_set_vector_table_base_arg_members(v, &arg, NULL);
    visit_end_struct(v, NULL);
    visit_free(v);
}
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

/* Dummy declaration to prevent empty .o file */
char qapi_dummy_qapi_commands_avatar_target_c;
