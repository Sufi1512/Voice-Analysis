"use client";

import dynamic from "next/dynamic";

// The invitation token is in the URL fragment, which only exists in the browser.
export const InviteClient = dynamic(() => import("./InviteForm").then((m) => m.InviteForm), { ssr: false });
