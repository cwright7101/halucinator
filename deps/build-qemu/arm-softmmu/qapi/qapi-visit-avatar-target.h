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

#ifndef QAPI_VISIT_AVATAR_TARGET_H
#define QAPI_VISIT_AVATAR_TARGET_H

#include "qapi/qapi-builtin-visit.h"
#include "qapi-types-avatar-target.h"


#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_enable_irq_arg_members(Visitor *v, q_obj_avatar_armv7m_enable_irq_arg *obj, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_inject_irq_arg_members(Visitor *v, q_obj_avatar_armv7m_inject_irq_arg *obj, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_ignore_irq_return_arg_members(Visitor *v, q_obj_avatar_armv7m_ignore_irq_return_arg *obj, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_unignore_irq_return_arg_members(Visitor *v, q_obj_avatar_armv7m_unignore_irq_return_arg *obj, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
bool visit_type_q_obj_avatar_armv7m_set_vector_table_base_arg_members(Visitor *v, q_obj_avatar_armv7m_set_vector_table_base_arg *obj, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#endif /* QAPI_VISIT_AVATAR_TARGET_H */
