// Audit actions with their own wording; anything else shows its code.
export const KNOWN_ACTIONS = [
  "organization.created",
  "organization.updated",
  "workspace.created",
  "invitation.created",
  "invitation.accepted",
  "member.added",
] as const;

export type KnownAction = (typeof KNOWN_ACTIONS)[number];

export function isKnownAction(action: string): action is KnownAction {
  return (KNOWN_ACTIONS as readonly string[]).includes(action);
}

/** Message key for an action: dots would read as nesting in next-intl, so they become "_". */
export function actionKey(action: KnownAction) {
  return action.replace(".", "_") as
    | "organization_created"
    | "organization_updated"
    | "workspace_created"
    | "invitation_created"
    | "invitation_accepted"
    | "member_added";
}
