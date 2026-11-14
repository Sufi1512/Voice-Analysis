// Shapes returned by NEXORA Core /v1 (platform/services/core).

export type Role =
  | "platform_owner"
  | "org_owner"
  | "org_admin"
  | "workspace_admin"
  | "developer"
  | "operator"
  | "viewer";

export type Permission =
  | "organization:read"
  | "organization:update"
  | "workspace:read"
  | "workspace:create"
  | "member:read"
  | "member:invite"
  | "member:manage"
  | "audit:read"
  | "platform:organizations";

export type User = { id: string; email: string; name: string };
export type Me = { user: User; is_platform_owner: boolean; mfa_passed: boolean };
export type MyOrganization = { id: string; name: string; slug: string; role: Role };
export type Organization = {
  id: string;
  name: string;
  slug: string;
  status: string;
  data_region: string;
  created_at: string;
  permissions: Permission[];
};
export type AuditEntry = {
  id: number;
  occurred_at: string;
  actor_type: "user" | "system";
  actor_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  workspace_id: string | null;
  details: Record<string, unknown>;
};
export type PlatformOrganization = {
  id: string;
  name: string;
  slug: string;
  status: "active" | "suspended";
  created_at: string;
  members: number;
};
