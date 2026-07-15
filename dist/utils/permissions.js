export function isAdminLike(member) { if (member?.permissions?.has?.('Administrator'))
    return true; const roleId = process.env.ADMIN_ROLE_ID; return Boolean(roleId && member?.roles?.cache?.has?.(roleId)); }
