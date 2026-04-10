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

#ifndef QAPI_COMMANDS_AVATAR_TARGET_H
#define QAPI_COMMANDS_AVATAR_TARGET_H

#include "qapi-types-avatar-target.h"

#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_avatar_armv7m_enable_irq(const char *irq_rx_queue_name, const char *irq_tx_queue_name, const char *rmem_rx_queue_name, const char *rmem_tx_queue_name, Error **errp);
void qmp_marshal_avatar_armv7m_enable_irq(QDict *args, QObject **ret, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */
#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_avatar_armv7m_disable_irq(Error **errp);
void qmp_marshal_avatar_armv7m_disable_irq(QDict *args, QObject **ret, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */
#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_avatar_armv7m_inject_irq(int64_t num_cpu, int64_t num_irq, Error **errp);
void qmp_marshal_avatar_armv7m_inject_irq(QDict *args, QObject **ret, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */
#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_avatar_armv7m_ignore_irq_return(int64_t num_irq, Error **errp);
void qmp_marshal_avatar_armv7m_ignore_irq_return(QDict *args, QObject **ret, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */
#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_avatar_armv7m_unignore_irq_return(int64_t num_irq, Error **errp);
void qmp_marshal_avatar_armv7m_unignore_irq_return(QDict *args, QObject **ret, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */
#if defined(CONFIG_AVATAR) && defined(TARGET_ARM)
void qmp_avatar_armv7m_set_vector_table_base(int64_t num_cpu, int64_t base, Error **errp);
void qmp_marshal_avatar_armv7m_set_vector_table_base(QDict *args, QObject **ret, Error **errp);
#endif /* defined(CONFIG_AVATAR) && defined(TARGET_ARM) */

#endif /* QAPI_COMMANDS_AVATAR_TARGET_H */
