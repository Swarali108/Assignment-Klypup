import path from "node:path";

export type Role = "admin" | "rm" | "viewer" | "head" | "newrm";

export const PASSWORD = "demo1234";

export const ACCOUNTS: Record<Role, { email: string; name: string; label: string }> = {
  admin: { email: "admin@aurelia.demo", name: "Asha Menon", label: "Admin" },
  rm: { email: "rm@aurelia.demo", name: "Rohan Kapoor", label: "Relationship manager" },
  viewer: { email: "viewer@aurelia.demo", name: "Vikram Shah", label: "Viewer" },
  head: { email: "head@aurelia.demo", name: "Meera Joshi", label: "Head of RMs" },
  newrm: { email: "new.rm@aurelia.demo", name: "Neha Iyer", label: "Relationship manager" },
};

export const ROLES = Object.keys(ACCOUNTS) as Role[];

export const AUTH_DIR = path.resolve(__dirname, "..", ".auth");
export const authFile = (role: Role) => path.join(AUTH_DIR, `${role}.json`);
export const SNAPSHOT_FILE = path.join(AUTH_DIR, "snapshot.json");
